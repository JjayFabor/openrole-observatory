import hashlib
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, event, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, SessionTransaction

from app.api.dependencies import get_job_query_service, get_source_query_service
from app.config import get_settings
from app.ingestion.errors import SourceSyncFailedError
from app.ingestion.orchestration import (
    JobProcessingOutcome,
    SnapshotIngestionOrchestrator,
)
from app.ingestion.source_processing import ProcessedSourceRecord
from app.jobs.absence_confirmation import AbsenceConfirmationService
from app.jobs.change_detection import TRACKED_JOB_FIELDS, diff_job_versions
from app.jobs.lifecycle_repository import JobLifecycleRepository
from app.jobs.models import Job, JobChangeEvent, JobLifecycleEvent, JobVersion
from app.jobs.presence_service import PresenceSetBuilder
from app.jobs.query_service import JobQueryService
from app.jobs.service import _build_comparable_version
from app.main import create_app
from app.pipeline_runs.models import PipelineRun
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.query_service import SourceQueryService
from app.storage.base import StoredObject
from app.storage.errors import StorageWriteError
from app.storage.filesystem import FilesystemObjectStorage
from tests.integration.ingestion.phase_two_scenarios import (
    INITIAL_TIME,
    PhaseTwoScenario,
    acceptance_board,
)
from tests.integration.ingestion.test_source_sync import (
    DatabaseContext,
    create_source,
    load_job_and_versions,
    load_runs,
    load_source,
)
from tests.integration.ingestion.test_source_sync import (
    database_context as database_context,
)
from tests.integration.ingestion.test_source_sync_lifecycle import events_for_job


@pytest_asyncio.fixture
async def scenario(
    database_context: DatabaseContext, tmp_path: Path
) -> AsyncIterator[PhaseTwoScenario]:
    scenario = PhaseTwoScenario(database_context, tmp_path)
    try:
        yield scenario
    finally:
        await scenario.close()


async def lifecycle_state(
    context: DatabaseContext, source_id: UUID
) -> dict[UUID, tuple[object, ...]]:
    async with context.session_factory() as session:
        jobs = list(
            await session.scalars(
                select(Job).where(Job.source_connection_id == source_id)
            )
        )
        return {
            job.id: (
                job.lifecycle_status,
                job.consecutive_absent_runs,
                job.absence_first_detected_at,
                job.no_longer_observed_at,
                job.reappeared_at,
            )
            for job in jobs
        }


async def source_event_ids(context: DatabaseContext, source_id: UUID) -> set[UUID]:
    async with context.session_factory() as session:
        return set(
            await session.scalars(
                select(JobLifecycleEvent.id)
                .join(Job)
                .where(Job.source_connection_id == source_id)
            )
        )


@pytest.mark.asyncio
async def test_authoritative_phase_two_history_and_api_story(
    database_context: DatabaseContext, scenario: PhaseTwoScenario
) -> None:
    source = await create_source(database_context)
    initial_body = acceptance_board()
    initial = await scenario.sync(source.id, initial_body)
    assert initial.jobs_new == initial.records_valid == 2
    first_job, first_versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    second_job, second_versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1002"
    )
    assert len(first_versions) == len(second_versions) == 1
    assert first_job.lifecycle_status == second_job.lifecycle_status == "observed"
    assert first_job.consecutive_absent_runs == second_job.consecutive_absent_runs == 0
    assert await source_event_ids(database_context, source.id) == set()

    unchanged = await scenario.sync(source.id, initial_body)
    assert (
        unchanged.jobs_unchanged == 2
        and unchanged.jobs_new == unchanged.jobs_changed == 0
    )
    unchanged_job, unchanged_versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert unchanged_versions[0].id == first_versions[0].id
    assert unchanged_job.last_seen_at == INITIAL_TIME + timedelta(days=1)
    async with database_context.session_factory() as session:
        observations = list(
            await session.scalars(
                select(SourceObservation).where(
                    SourceObservation.source_connection_id == source.id
                )
            )
        )
    assert len(observations) == 4

    changed = await scenario.sync(source.id, acceptance_board(workplace="hybrid"))
    assert changed.jobs_changed == 1 and changed.jobs_unchanged == 1
    async with database_context.session_factory() as session:
        changes = list(
            await session.scalars(
                select(JobChangeEvent).where(JobChangeEvent.job_id == first_job.id)
            )
        )
    assert [
        (event.field_name, event.old_value, event.new_value) for event in changes
    ] == [("workplace_type", "remote", "hybrid")]
    multiple_body = acceptance_board(workplace="hybrid", multiple_changes=True)
    multiple = await scenario.sync(source.id, multiple_body)
    assert multiple.jobs_changed == 1 and multiple.jobs_unchanged == 1
    _, versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert [version.version_number for version in versions] == [1, 2, 3]
    immutable_content = [
        tuple(getattr(version, field) for field in TRACKED_JOB_FIELDS)
        for version in versions
    ]

    missing_body = acceptance_board((1001,), workplace="hybrid", multiple_changes=True)
    first_absence = await scenario.sync(source.id, missing_body)
    absent, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1002"
    )
    assert absent.lifecycle_status == "observed" and absent.consecutive_absent_runs == 1
    assert (
        first_absence.lifecycle is not None
        and first_absence.lifecycle.jobs_confirmed_not_observed == 0
    )
    # A completed run's first absence must not also count as its second absence.
    repeated = await AbsenceConfirmationService(
        database_context.session_factory
    ).confirm_absences(first_absence.pipeline_run_id)
    assert (
        repeated.confirmed_not_observed == 0 and repeated.skipped_already_applied == 1
    )

    reset = await scenario.sync(source.id, multiple_body)
    reset_job, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1002"
    )
    assert (
        reset_job.consecutive_absent_runs == 0
        and reset_job.absence_first_detected_at is None
    )
    assert (
        reset.lifecycle is not None
        and reset.lifecycle.tentative_absences_reset == 1
        and reset.lifecycle.jobs_reappeared == 0
    )
    first_cycle_start = await scenario.sync(source.id, missing_body)
    first_confirmation = await scenario.sync(source.id, missing_body)
    confirmed_job, confirmed_versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1002"
    )
    assert (
        confirmed_job.lifecycle_status == "not_observed"
        and confirmed_job.consecutive_absent_runs == 2
    )
    assert confirmed_job.absence_first_detected_at == INITIAL_TIME + timedelta(days=6)
    assert confirmed_job.no_longer_observed_at == INITIAL_TIME + timedelta(days=7)
    assert len(confirmed_versions) == 1
    same_return = await scenario.sync(source.id, multiple_body)
    assert (
        same_return.jobs_changed == 0
        and same_return.lifecycle is not None
        and same_return.lifecycle.jobs_reappeared == 1
    )
    _, returned_versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1002"
    )
    assert len(returned_versions) == 1
    second_cycle_start = await scenario.sync(source.id, missing_body)
    second_confirmation = await scenario.sync(source.id, missing_body)
    changed_return_body = acceptance_board(
        workplace="hybrid", multiple_changes=True, changed_return=True
    )
    changed_return = await scenario.sync(source.id, changed_return_body)
    assert (
        changed_return.jobs_changed == 1
        and changed_return.lifecycle is not None
        and changed_return.lifecycle.jobs_reappeared == 1
    )
    returned_job, returned_versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1002"
    )
    assert (
        returned_job.lifecycle_status == "observed"
        and returned_job.consecutive_absent_runs == 0
    )
    assert returned_job.absence_first_detected_at is None
    assert returned_job.no_longer_observed_at == INITIAL_TIME + timedelta(days=10)
    assert (
        returned_job.reappeared_at
        == returned_job.last_seen_at
        == INITIAL_TIME + timedelta(days=11)
    )
    assert len(returned_versions) == 2
    history = await events_for_job(database_context, returned_job.id)
    assert [event.event_type for event in history] == [
        "absence_detected",
        "absence_detected",
        "not_observed_confirmed",
        "reappeared",
        "absence_detected",
        "not_observed_confirmed",
        "reappeared",
    ]
    assert [event.pipeline_run_id for event in history] == [
        first_absence.pipeline_run_id,
        first_cycle_start.pipeline_run_id,
        first_confirmation.pipeline_run_id,
        same_return.pipeline_run_id,
        second_cycle_start.pipeline_run_id,
        second_confirmation.pipeline_run_id,
        changed_return.pipeline_run_id,
    ]

    # Inspect the same actual history through the production read services/routes.
    app = create_app(get_settings())
    jobs, sources = (
        JobQueryService(database_context.session_factory),
        SourceQueryService(database_context.session_factory),
    )
    app.dependency_overrides[get_job_query_service] = lambda: jobs
    app.dependency_overrides[get_source_query_service] = lambda: sources
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        detail = await client.get(f"/api/v1/jobs/{returned_job.id}")
        assert detail.status_code == 200
        body = detail.json()
        assert (
            body["lifecycle_status"] == "observed"
            and body["consecutive_absent_runs"] == 0
        )
        assert body["current_version"]["version_number"] == 2
        assert body["no_longer_observed_at"] and body["reappeared_at"]
        version_body = (
            await client.get(f"/api/v1/jobs/{first_job.id}/versions")
        ).json()
        assert [item["version_number"] for item in version_body["items"]] == [1, 2, 3]
        assert [item["is_current"] for item in version_body["items"]] == [
            False,
            False,
            True,
        ]
        change_body = (await client.get(f"/api/v1/jobs/{first_job.id}/changes")).json()
        transition_fields = [
            item["field_name"]
            for item in change_body["items"]
            if item["to_version_number"] == 3
        ]
        assert transition_fields == [
            "employment_type",
            "location_text",
            "salary_max",
            "salary_min",
        ]
        lifecycle_body = (
            await client.get(f"/api/v1/jobs/{returned_job.id}/lifecycle")
        ).json()
        assert [event["id"] for event in lifecycle_body["events"]] == [
            str(event.id) for event in history
        ]
        prior_success = (
            await load_source(database_context, source.id)
        ).last_successful_sync_at
        with pytest.raises(SourceSyncFailedError):
            await scenario.sync(source.id, changed_return_body, failure="timeout")
        health = (await client.get(f"/api/v1/sources/{source.id}")).json()
        assert health["latest_run"]["status"] == "failed"
        assert health["latest_run"]["error_code"] == "SOURCE_REQUEST_TIMEOUT"
        assert prior_success is not None
        assert health["last_successful_sync_at"] == prior_success.isoformat().replace(
            "+00:00", "Z"
        )
        assert health["last_attempted_sync_at"] != health["last_successful_sync_at"]

    _, final_versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert [
        tuple(getattr(version, field) for field in TRACKED_JOB_FIELDS)
        for version in final_versions
    ] == immutable_content
    assert sum(version.is_current for version in final_versions) == 1
    async with database_context.session_factory() as session:
        source_jobs = list(
            await session.scalars(
                select(Job).where(Job.source_connection_id == source.id)
            )
        )
        all_changes = list(
            await session.scalars(
                select(JobChangeEvent)
                .join(Job)
                .where(Job.source_connection_id == source.id)
            )
        )
        for job in source_jobs:
            job_versions = list(
                await session.scalars(
                    select(JobVersion)
                    .where(JobVersion.job_id == job.id)
                    .order_by(JobVersion.version_number)
                )
            )
            for previous, current in zip(job_versions, job_versions[1:], strict=False):
                derived = diff_job_versions(
                    _build_comparable_version(previous),
                    _build_comparable_version(current),
                )
                events = [
                    event for event in all_changes if event.to_version_id == current.id
                ]
                assert {event.field_name for event in events} == {
                    change.field_name for change in derived
                }
                assert all(
                    event.job_id == previous.job_id == current.job_id
                    and event.from_version_id == previous.id
                    for event in events
                )
                assert current.version_number == previous.version_number + 1
            for version in job_versions:
                observation = await session.get(
                    SourceObservation, version.source_observation_id
                )
                assert observation is not None
                snapshot = await session.get(RawSnapshot, observation.raw_snapshot_id)
                assert snapshot is not None
                run = await session.get(PipelineRun, snapshot.pipeline_run_id)
                assert (
                    run is not None
                    and run.id == observation.pipeline_run_id
                    and run.source_connection_id == source.id
                )
                raw = await scenario.storage.get_bytes(key=snapshot.r2_object_key)
                assert hashlib.sha256(raw).hexdigest() == snapshot.content_hash
                assert observation.external_job_id == job.external_job_id
        assert len(
            {
                (event.from_version_id, event.to_version_id, event.field_name)
                for event in all_changes
            }
        ) == len(all_changes)
        # Version history remains reconstructable without its derived explanations.
        await session.execute(
            delete(JobChangeEvent).where(
                JobChangeEvent.job_id.in_([job.id for job in source_jobs])
            )
        )
        await session.flush()
        assert (await jobs.versions(first_job.id, limit=100, offset=0)) is not None
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_absences", [0, 1, 2])
@pytest.mark.parametrize("quarantine", ["known", "unknown"])
async def test_partial_source_evidence_remains_conservative_end_to_end(
    database_context: DatabaseContext,
    scenario: PhaseTwoScenario,
    previous_absences: int,
    quarantine: str,
) -> None:
    source = await create_source(database_context)
    await scenario.sync(source.id, acceptance_board())
    for _ in range(previous_absences):
        await scenario.sync(source.id, acceptance_board((1001,)))
    before = await lifecycle_state(database_context, source.id)
    events_before = await source_event_ids(database_context, source.id)
    result = await scenario.sync(
        source.id, acceptance_board(workplace="hybrid", quarantine=quarantine)
    )
    assert result.status.value == "completed_with_errors"
    assert result.jobs_changed == 1 and result.records_quarantined == 1
    async with database_context.session_factory() as session:
        presence = await PresenceSetBuilder(session).build_presence_set(
            result.pipeline_run_id
        )
    assert presence.presence_reconciliation_safe is (quarantine == "known")
    assert result.lifecycle is not None and result.lifecycle.performed is (
        quarantine == "known"
    )
    if quarantine == "unknown":
        assert await lifecycle_state(database_context, source.id) == before
    else:
        target, _ = await load_job_and_versions(
            database_context, source_connection_id=source.id, external_job_id="1002"
        )
        assert target.consecutive_absent_runs == (2 if previous_absences == 2 else 0)
        assert target.lifecycle_status == (
            "not_observed" if previous_absences == 2 else "observed"
        )
        assert target.reappeared_at is None
    assert await source_event_ids(database_context, source.id) == events_before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["timeout", "503", "storage", "invalid_json", "database", "lifecycle_event"],
)
async def test_failed_sync_preserves_existing_lifecycle_end_to_end(
    database_context: DatabaseContext,
    scenario: PhaseTwoScenario,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    source = await create_source(database_context)
    await scenario.sync(source.id, acceptance_board())
    await scenario.sync(source.id, acceptance_board((1001,)))
    before = await lifecycle_state(database_context, source.id)
    events_before = await source_event_ids(database_context, source.id)
    prior_success = (
        await load_source(database_context, source.id)
    ).last_successful_sync_at
    if failure == "storage":

        async def fail_storage(*args: object, **kwargs: object) -> None:
            raise StorageWriteError("private storage failure")

        monkeypatch.setattr(FilesystemObjectStorage, "put_bytes", fail_storage)
    elif failure == "database":

        async def fail_record(
            self: SnapshotIngestionOrchestrator, record: ProcessedSourceRecord
        ) -> JobProcessingOutcome:
            raise SQLAlchemyError("private database failure")

        monkeypatch.setattr(SnapshotIngestionOrchestrator, "_route_record", fail_record)
    elif failure == "lifecycle_event":
        original = JobLifecycleRepository.add_lifecycle_events

        async def fail_event(
            self: JobLifecycleRepository, events: list[JobLifecycleEvent]
        ) -> None:
            await original(self, events)
            if events:
                raise SQLAlchemyError("private event persistence failure after flush")

        monkeypatch.setattr(JobLifecycleRepository, "add_lifecycle_events", fail_event)
    body = b'{"jobs":' if failure == "invalid_json" else acceptance_board((1001,))
    with pytest.raises(SourceSyncFailedError) as caught:
        await scenario.sync(
            source.id, body, failure=failure if failure in {"timeout", "503"} else None
        )
    assert "private" not in caught.value.safe_message
    assert (await load_runs(database_context, source.id))[-1].status == "failed"
    assert await lifecycle_state(database_context, source.id) == before
    assert await source_event_ids(database_context, source.id) == events_before
    assert (
        await load_source(database_context, source.id)
    ).last_successful_sync_at == prior_success


@pytest.mark.asyncio
async def test_empty_successful_board_and_source_isolation_end_to_end(
    database_context: DatabaseContext, scenario: PhaseTwoScenario
) -> None:
    source, other = (
        await create_source(database_context),
        await create_source(database_context),
    )
    await scenario.sync(source.id, acceptance_board())
    await scenario.sync(other.id, acceptance_board())
    other_before = await lifecycle_state(database_context, other.id)
    first = await scenario.sync(source.id, acceptance_board(()))
    assert (
        first.records_fetched == 0
        and first.lifecycle is not None
        and first.lifecycle.first_absences_detected == 2
    )
    assert all(
        state[0] == "observed" and state[1] == 1
        for state in (await lifecycle_state(database_context, source.id)).values()
    )
    second = await scenario.sync(source.id, acceptance_board(()))
    assert (
        second.records_fetched == 0
        and second.lifecycle is not None
        and second.lifecycle.jobs_confirmed_not_observed == 2
    )
    assert all(
        state[0] == "not_observed" and state[1] == 2
        for state in (await lifecycle_state(database_context, source.id)).values()
    )
    assert await lifecycle_state(database_context, other.id) == other_before
    assert await source_event_ids(database_context, other.id) == set()
    _, versions = await load_job_and_versions(
        database_context, source_connection_id=other.id, external_job_id="1001"
    )
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_hundred_job_performance_sanity(
    database_context: DatabaseContext,
    scenario: PhaseTwoScenario,
) -> None:
    source = await create_source(database_context)
    ids = tuple(range(1001, 1101))
    started = time.monotonic()
    initial = await scenario.sync(source.id, acceptance_board(ids))
    unchanged = await scenario.sync(source.id, acceptance_board(ids))
    subset = await scenario.sync(
        source.id, acceptance_board(ids[:-10], workplace="hybrid")
    )
    elapsed = time.monotonic() - started
    assert initial.jobs_new == unchanged.jobs_unchanged == 100
    assert subset.jobs_changed == 1 and subset.jobs_unchanged == 89
    assert (
        subset.lifecycle is not None and subset.lifecycle.first_absences_detected == 10
    )
    print(f"100-job initial/unchanged/subset scenario: {elapsed:.2f}s")


@pytest.mark.asyncio
async def test_application_transactions_do_not_span_http_or_storage(
    database_context: DatabaseContext,
    scenario: PhaseTwoScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = await create_source(database_context)
    active_sessions: set[Session] = set()
    io_checks: list[str] = []

    def began(
        session: Session, transaction: SessionTransaction, connection: Connection
    ) -> None:
        active_sessions.add(session)

    def ended(session: Session, transaction: SessionTransaction) -> None:
        if transaction.parent is None:
            active_sessions.discard(session)

    async def request_hook(request: httpx.Request) -> None:
        assert not active_sessions
        io_checks.append("http")

    original_put, original_get = scenario.storage.put_bytes, scenario.storage.get_bytes

    async def put(*, key: str, data: bytes, content_type: str) -> StoredObject:
        assert not active_sessions
        io_checks.append("put")
        return await original_put(key=key, data=data, content_type=content_type)

    async def get(*, key: str) -> bytes:
        assert not active_sessions
        io_checks.append("get")
        return await original_get(key=key)

    monkeypatch.setattr(scenario.storage, "put_bytes", put)
    monkeypatch.setattr(scenario.storage, "get_bytes", get)
    scenario.http_client.event_hooks["request"] = [request_hook]
    event.listen(Session, "after_begin", began)
    event.listen(Session, "after_transaction_end", ended)
    try:
        await scenario.sync(source.id, acceptance_board())
        await scenario.sync(source.id, acceptance_board((1001,)))
        assert not active_sessions
        assert io_checks == ["http", "put", "get", "http", "put", "get"]
    finally:
        event.remove(Session, "after_begin", began)
        event.remove(Session, "after_transaction_end", ended)
