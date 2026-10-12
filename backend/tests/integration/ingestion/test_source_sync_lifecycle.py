import json
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ingestion.errors import SourceSyncFailedError
from app.ingestion.locking import PostgresSourceRunLock
from app.ingestion.orchestration import (
    JobProcessingOutcome,
    SnapshotIngestionOrchestrator,
)
from app.ingestion.source_processing import ProcessedSourceRecord
from app.ingestion.sync import SourceSyncService
from app.jobs.absence_confirmation import (
    AbsenceConfirmationResult,
    AbsenceConfirmationService,
)
from app.jobs.first_absence import (
    FirstAbsenceDetectionResult,
    FirstAbsenceDetectionService,
)
from app.jobs.lifecycle_reconciliation import LifecycleReconciliationService
from app.jobs.models import Job, JobChangeEvent, JobLifecycleEvent
from app.jobs.presence import PresenceRun, PresenceUnsafeReason
from app.jobs.presence_service import PresenceSetBuilder
from app.jobs.present_reconciliation import (
    PresentJobReconciliationResult,
    PresentJobReconciliationService,
)
from app.pipeline_runs.errors import SourceSyncAlreadyRunningError
from app.pipeline_runs.models import PipelineRun
from app.pipeline_runs.schemas import PipelineMetrics
from app.pipeline_runs.service import PipelineRunService
from app.sources.greenhouse.client import GreenhouseFetchResult
from app.storage.filesystem import FilesystemObjectStorage
from tests.integration.ingestion.test_source_sync import (
    FIRST_RETRIEVED_AT,
    DatabaseContext,
    QueueGreenhouseClient,
    build_sync_service,
    create_source,
    fetch_result,
    fixture_bytes,
    load_job_and_versions,
    load_runs,
    load_source,
)
from tests.integration.ingestion.test_source_sync import (
    database_context as database_context,
)


def board(
    *, omit_target: bool = False, changed: bool = False, quarantine: str | None = None
) -> bytes:
    document = json.loads(fixture_bytes("jobs_v2.json" if changed else "jobs_v1.json"))
    if omit_target:
        document["jobs"] = [job for job in document["jobs"] if job["id"] != 1001]
    elif quarantine is not None:
        target = next(job for job in document["jobs"] if job["id"] == 1001)
        del target["title" if quarantine == "known" else "id"]
    return json.dumps(document).encode()


def service_for_boards(
    context: DatabaseContext, tmp_path: Path, bodies: Sequence[bytes]
) -> SourceSyncService:
    results: list[GreenhouseFetchResult | Exception] = [
        fetch_result(body, FIRST_RETRIEVED_AT + timedelta(days=index))
        for index, body in enumerate(bodies)
    ]
    return build_sync_service(
        context,
        greenhouse_client=QueueGreenhouseClient(results),
        object_storage=FilesystemObjectStorage(tmp_path),
    )


async def events_for_job(
    context: DatabaseContext, job_id: UUID
) -> list[JobLifecycleEvent]:
    async with context.session_factory() as session:
        return list(
            await session.scalars(
                select(JobLifecycleEvent)
                .where(JobLifecycleEvent.job_id == job_id)
                .order_by(JobLifecycleEvent.occurred_at)
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_full_absence_and_reappearance_cycle_preserves_both_histories(
    database_context: DatabaseContext, tmp_path: Path, changed: bool
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(
        database_context,
        tmp_path,
        [
            board(),
            board(omit_target=True),
            board(omit_target=True),
            board(changed=changed),
        ],
    )
    first = await service.sync_source(source.id)
    assert first.lifecycle is not None and first.lifecycle.performed
    assert first.lifecycle.first_absences_detected == 0
    second = await service.sync_source(source.id)
    job, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert job.lifecycle_status == "observed"
    assert job.consecutive_absent_runs == 1
    assert job.absence_first_detected_at == FIRST_RETRIEVED_AT + timedelta(days=1)
    assert second.lifecycle is not None
    assert second.lifecycle.first_absences_detected == 1
    assert second.lifecycle.jobs_confirmed_not_observed == 0
    third = await service.sync_source(source.id)
    job, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert job.lifecycle_status == "not_observed"
    assert job.consecutive_absent_runs == 2
    assert job.no_longer_observed_at == FIRST_RETRIEVED_AT + timedelta(days=2)
    assert (
        third.lifecycle is not None and third.lifecycle.jobs_confirmed_not_observed == 1
    )
    fourth = await service.sync_source(source.id)
    job, versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert job.lifecycle_status == "observed"
    assert job.consecutive_absent_runs == 0
    assert job.absence_first_detected_at is None
    assert job.no_longer_observed_at == FIRST_RETRIEVED_AT + timedelta(days=2)
    assert (
        job.reappeared_at == job.last_seen_at == FIRST_RETRIEVED_AT + timedelta(days=3)
    )
    assert job.first_seen_at == FIRST_RETRIEVED_AT
    assert len(versions) == (2 if changed else 1)
    assert fourth.lifecycle is not None and fourth.lifecycle.jobs_reappeared == 1
    events = await events_for_job(database_context, job.id)
    assert [event.event_type for event in events] == [
        "absence_detected",
        "not_observed_confirmed",
        "reappeared",
    ]
    assert [event.pipeline_run_id for event in events] == [
        second.pipeline_run_id,
        third.pipeline_run_id,
        fourth.pipeline_run_id,
    ]
    async with database_context.session_factory() as session:
        changes = list(
            await session.scalars(
                select(JobChangeEvent).where(JobChangeEvent.job_id == job.id)
            )
        )
    assert bool(changes) is changed
    assert all(
        result.status.value == "completed" for result in (first, second, third, fourth)
    )


@pytest.mark.asyncio
async def test_tentative_absence_clears_without_reappearance_event(
    database_context: DatabaseContext, tmp_path: Path
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(
        database_context, tmp_path, [board(), board(omit_target=True), board()]
    )
    await service.sync_source(source.id)
    await service.sync_source(source.id)
    result = await service.sync_source(source.id)
    job, versions = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert job.lifecycle_status == "observed"
    assert job.consecutive_absent_runs == 0
    assert job.absence_first_detected_at is None
    assert job.reappeared_at is None
    assert len(versions) == 1
    assert result.lifecycle is not None
    assert result.lifecycle.tentative_absences_reset == 1
    assert result.lifecycle.jobs_reappeared == 0
    assert [
        event.event_type for event in await events_for_job(database_context, job.id)
    ] == ["absence_detected"]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_absences", [0, 1, 2])
async def test_unsafe_partial_run_skips_lifecycle_for_every_prior_state(
    database_context: DatabaseContext, tmp_path: Path, previous_absences: int
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(
        database_context,
        tmp_path,
        [
            board(),
            *[board(omit_target=True)] * previous_absences,
            board(quarantine="unknown"),
        ],
    )
    for _ in range(previous_absences + 1):
        await service.sync_source(source.id)
    before, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    prior_events = await events_for_job(database_context, before.id)
    result = await service.sync_source(source.id)
    stored, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    for field in (
        "lifecycle_status",
        "consecutive_absent_runs",
        "absence_first_detected_at",
        "no_longer_observed_at",
        "reappeared_at",
    ):
        assert getattr(stored, field) == getattr(before, field)
    assert [
        event.id for event in await events_for_job(database_context, before.id)
    ] == [event.id for event in prior_events]
    assert result.status.value == "completed_with_errors"
    assert result.records_valid == 3 and result.records_quarantined == 1
    assert result.lifecycle is not None and not result.lifecycle.performed
    assert (
        result.lifecycle.skipped_reason
        is PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS
    )
    assert (
        result.lifecycle.first_absences_detected
        == result.lifecycle.jobs_reappeared
        == result.lifecycle.jobs_confirmed_not_observed
        == result.lifecycle.tentative_absences_reset
        == 0
    )
    assert (
        await load_source(database_context, source.id)
    ).last_successful_sync_at == result.completed_at


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_absences", [1, 2])
async def test_safe_partial_run_uses_quarantine_as_presence_only(
    database_context: DatabaseContext, tmp_path: Path, previous_absences: int
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(
        database_context,
        tmp_path,
        [
            board(),
            *[board(omit_target=True)] * previous_absences,
            board(quarantine="known"),
        ],
    )
    for _ in range(previous_absences + 1):
        await service.sync_source(source.id)
    result = await service.sync_source(source.id)
    job, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert result.status.value == "completed_with_errors"
    assert result.lifecycle is not None and result.lifecycle.performed
    assert (
        result.lifecycle.jobs_reappeared
        == result.lifecycle.first_absences_detected
        == 0
    )
    assert job.last_seen_at == FIRST_RETRIEVED_AT
    if previous_absences == 1:
        assert job.lifecycle_status == "observed"
        assert job.consecutive_absent_runs == 0
        assert job.absence_first_detected_at is None
        assert result.lifecycle.tentative_absences_reset == 1
    else:
        assert job.lifecycle_status == "not_observed"
        assert job.consecutive_absent_runs == 2
        assert result.lifecycle.tentative_absences_reset == 0


@pytest.mark.asyncio
async def test_empty_boards_require_two_runs_and_preserve_other_source(
    database_context: DatabaseContext, tmp_path: Path
) -> None:
    source, other = (
        await create_source(database_context),
        await create_source(database_context),
    )
    service = service_for_boards(
        database_context, tmp_path, [board(), board(), b'{"jobs": []}', b'{"jobs": []}']
    )
    await service.sync_source(source.id)
    await service.sync_source(other.id)
    first_empty = await service.sync_source(source.id)
    for external_id in ("1001", "1002", "1003", "1004"):
        job, _ = await load_job_and_versions(
            database_context,
            source_connection_id=source.id,
            external_job_id=external_id,
        )
        assert job.lifecycle_status == "observed" and job.consecutive_absent_runs == 1
    second_empty = await service.sync_source(source.id)
    assert (
        first_empty.lifecycle is not None
        and first_empty.lifecycle.first_absences_detected == 4
    )
    assert (
        second_empty.lifecycle is not None
        and second_empty.lifecycle.jobs_confirmed_not_observed == 4
    )
    for external_id in ("1001", "1002", "1003", "1004"):
        job, _ = await load_job_and_versions(
            database_context,
            source_connection_id=source.id,
            external_job_id=external_id,
        )
        untouched, _ = await load_job_and_versions(
            database_context, source_connection_id=other.id, external_job_id=external_id
        )
        assert (
            job.lifecycle_status == "not_observed" and job.consecutive_absent_runs == 2
        )
        assert (
            untouched.lifecycle_status == "observed"
            and untouched.consecutive_absent_runs == 0
        )
        assert untouched.last_seen_at == FIRST_RETRIEVED_AT + timedelta(days=1)
        assert await events_for_job(database_context, untouched.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage",
    [
        "presence_set",
        "present_reconciliation",
        "absence_confirmation",
        "first_absence_detection",
    ],
)
async def test_lifecycle_failure_fails_run_retains_metrics_and_releases_lock(
    database_context: DatabaseContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stage: str,
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(
        database_context, tmp_path, [board(), board(omit_target=True), board()]
    )
    await service.sync_source(source.id)
    await service.sync_source(source.id)
    prior_success = (
        await load_source(database_context, source.id)
    ).last_successful_sync_at

    async def fail(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("private lifecycle failure detail")

    target, method = {
        "presence_set": (PresenceSetBuilder, "build_presence_set"),
        "present_reconciliation": (
            PresentJobReconciliationService,
            "reconcile_present_jobs",
        ),
        "absence_confirmation": (AbsenceConfirmationService, "confirm_absences"),
        "first_absence_detection": (
            FirstAbsenceDetectionService,
            "detect_first_absences",
        ),
    }[stage]
    monkeypatch.setattr(target, method, fail)
    with pytest.raises(SourceSyncFailedError) as caught:
        await service.sync_source(source.id)
    assert caught.value.code == "DATABASE_WRITE_FAILED"
    assert "private" not in caught.value.safe_message
    runs = await load_runs(database_context, source.id)
    failed = runs[-1]
    assert failed.status == "failed"
    assert failed.records_fetched == failed.records_valid == failed.jobs_unchanged == 4
    assert (
        await load_source(database_context, source.id)
    ).last_successful_sync_at == prior_success
    job, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert job.consecutive_absent_runs == 1
    assert job.lifecycle_status == "observed"
    assert [
        event.event_type for event in await events_for_job(database_context, job.id)
    ] == ["absence_detected"]
    assert any(
        record.getMessage() == "lifecycle_reconciliation_failed"
        and getattr(record, "stage", None) == stage
        and getattr(record, "pipeline_run_id", None) == str(failed.id)
        for record in caplog.records
    )
    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("failure_point", ["after_flush", "before_commit"])
async def test_finalization_failure_rolls_back_every_lifecycle_action(
    database_context: DatabaseContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    partial: bool,
    failure_point: str,
) -> None:
    source = await create_source(database_context)

    def selected(ids: set[int]) -> bytes:
        document = json.loads(board())
        document["jobs"] = [job for job in document["jobs"] if job["id"] in ids]
        return json.dumps(document).encode()

    final_document = json.loads(selected({1001, 1003}))
    if partial:
        final_document["jobs"].append({"id": 9999})
    service = service_for_boards(
        database_context,
        tmp_path,
        [
            board(),
            selected({1001, 1002, 1004}),
            selected({1001, 1002, 1004}),
            selected({1004}),
            json.dumps(final_document).encode(),
        ],
    )
    for _ in range(4):
        await service.sync_source(source.id)
    async with database_context.session_factory() as session:
        jobs = list(
            await session.scalars(
                select(Job).where(Job.source_connection_id == source.id)
            )
        )
    before = {
        job.id: (
            job.lifecycle_status,
            job.consecutive_absent_runs,
            job.absence_first_detected_at,
            job.no_longer_observed_at,
            job.reappeared_at,
        )
        for job in jobs
    }
    prior_event_ids = {
        event.id
        for job in jobs
        for event in await events_for_job(database_context, job.id)
    }
    prior_success = (
        await load_source(database_context, source.id)
    ).last_successful_sync_at
    original = (
        PipelineRunService.complete_with_errors
        if partial
        else PipelineRunService.complete
    )

    async def fail_after_flush(
        self: PipelineRunService,
        run_id: UUID,
        metrics: PipelineMetrics,
        *,
        session: AsyncSession | None = None,
    ) -> PipelineRun:
        assert session is not None
        staged = list(
            await session.scalars(
                select(Job).where(Job.source_connection_id == source.id)
            )
        )
        by_id = {job.external_job_id: job for job in staged}
        assert by_id["1001"].consecutive_absent_runs == 0  # tentative reset
        assert by_id["1002"].lifecycle_status == "not_observed"  # confirmation
        assert by_id["1003"].lifecycle_status == "observed"  # reappearance
        assert by_id["1004"].consecutive_absent_runs == 1  # first absence
        result = await original(self, run_id, metrics, session=session)
        if failure_point == "after_flush":
            raise SQLAlchemyError("finalization failed after its database flush")

        def fail_commit(_: Session) -> None:
            raise SQLAlchemyError("final lifecycle transaction could not commit")

        event.listen(session.sync_session, "before_commit", fail_commit, once=True)
        return result

    monkeypatch.setattr(
        PipelineRunService,
        "complete_with_errors" if partial else "complete",
        fail_after_flush,
    )
    with pytest.raises(SourceSyncFailedError):
        await service.sync_source(source.id)
    failed = (await load_runs(database_context, source.id))[-1]
    assert failed.status == "failed"
    assert failed.records_valid == failed.jobs_unchanged == 2
    assert failed.records_quarantined == int(partial)
    async with database_context.session_factory() as session:
        jobs = list(
            await session.scalars(
                select(Job).where(Job.source_connection_id == source.id)
            )
        )
    assert {
        job.id: (
            job.lifecycle_status,
            job.consecutive_absent_runs,
            job.absence_first_detected_at,
            job.no_longer_observed_at,
            job.reappeared_at,
        )
        for job in jobs
    } == before
    assert {
        event.id
        for job in jobs
        for event in await events_for_job(database_context, job.id)
    } == prior_event_ids
    assert (
        await load_source(database_context, source.id)
    ).last_successful_sync_at == prior_success
    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_run_stays_running_and_lock_is_held_until_finalization(
    database_context: DatabaseContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(
        database_context, tmp_path, [board(), board(omit_target=True)]
    )
    await service.sync_source(source.id)
    prior_success = (
        await load_source(database_context, source.id)
    ).last_successful_sync_at
    order: list[str] = []

    async def check_boundary(run_id: UUID) -> None:
        async with database_context.session_factory() as session:
            run = await session.get(PipelineRun, run_id)
        assert run is not None and run.status == "running" and run.completed_at is None
        assert (
            await load_source(database_context, source.id)
        ).last_successful_sync_at == prior_success
        with pytest.raises(SourceSyncAlreadyRunningError):
            async with PostgresSourceRunLock(database_context.engine).hold(source.id):
                pytest.fail("source lock released before finalization")

    original_present = PresentJobReconciliationService.reconcile_present_jobs
    original_confirm = AbsenceConfirmationService.confirm_absences
    original_first = FirstAbsenceDetectionService.detect_first_absences
    original_complete = PipelineRunService.complete

    async def present(
        self: PresentJobReconciliationService,
        run_id: UUID,
        *,
        processed_run: PresenceRun | None = None,
        session: AsyncSession | None = None,
    ) -> PresentJobReconciliationResult:
        await check_boundary(run_id)
        order.append("present")
        return await original_present(
            self, run_id, processed_run=processed_run, session=session
        )

    async def confirm(
        self: AbsenceConfirmationService,
        run_id: UUID,
        *,
        processed_run: PresenceRun | None = None,
        session: AsyncSession | None = None,
    ) -> AbsenceConfirmationResult:
        await check_boundary(run_id)
        order.append("confirm")
        return await original_confirm(
            self, run_id, processed_run=processed_run, session=session
        )

    async def first(
        self: FirstAbsenceDetectionService,
        run_id: UUID,
        *,
        processed_run: PresenceRun | None = None,
        session: AsyncSession | None = None,
    ) -> FirstAbsenceDetectionResult:
        await check_boundary(run_id)
        order.append("first")
        return await original_first(
            self, run_id, processed_run=processed_run, session=session
        )

    async def complete(
        self: PipelineRunService,
        run_id: UUID,
        metrics: PipelineMetrics,
        *,
        session: AsyncSession | None = None,
    ) -> PipelineRun:
        await check_boundary(run_id)
        assert order == ["present", "confirm", "first"]
        order.append("finalize")
        job, _ = await load_job_and_versions(
            database_context, source_connection_id=source.id, external_job_id="1001"
        )
        assert job.consecutive_absent_runs == 1 and job.lifecycle_status == "observed"
        return await original_complete(self, run_id, metrics, session=session)

    monkeypatch.setattr(
        PresentJobReconciliationService, "reconcile_present_jobs", present
    )
    monkeypatch.setattr(AbsenceConfirmationService, "confirm_absences", confirm)
    monkeypatch.setattr(FirstAbsenceDetectionService, "detect_first_absences", first)
    monkeypatch.setattr(PipelineRunService, "complete", complete)
    result = await service.sync_source(source.id)
    assert order == ["present", "confirm", "first", "finalize"]
    assert (
        await load_source(database_context, source.id)
    ).last_successful_sync_at == result.completed_at
    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_partial_record_failure_retains_progress_without_lifecycle(
    database_context: DatabaseContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(database_context, tmp_path, [board()])
    original = SnapshotIngestionOrchestrator._route_record
    calls = 0

    async def route(
        self: SnapshotIngestionOrchestrator, record: ProcessedSourceRecord
    ) -> JobProcessingOutcome:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SQLAlchemyError("private record database failure")
        return await original(self, record)

    async def unexpected_lifecycle(
        self: LifecycleReconciliationService, processed_run: PresenceRun
    ) -> None:
        pytest.fail("failed record processing reached lifecycle reconciliation")

    monkeypatch.setattr(SnapshotIngestionOrchestrator, "_route_record", route)
    monkeypatch.setattr(
        LifecycleReconciliationService, "reconcile_processed_run", unexpected_lifecycle
    )
    with pytest.raises(SourceSyncFailedError) as caught:
        await service.sync_source(source.id)
    assert caught.value.code == "DATABASE_WRITE_FAILED"
    failed = (await load_runs(database_context, source.id))[0]
    assert failed.status == "failed"
    assert failed.records_fetched == 4
    assert failed.records_valid == failed.jobs_new == 1
    assert failed.records_quarantined == 0
    assert (
        await load_source(database_context, source.id)
    ).last_successful_sync_at is None
    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_later_lifecycle_failure_rolls_back_prior_confirmation(
    database_context: DatabaseContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = await create_source(database_context)
    service = service_for_boards(
        database_context,
        tmp_path,
        [board(), board(omit_target=True), board(omit_target=True)],
    )
    await service.sync_source(source.id)
    await service.sync_source(source.id)
    prior_success = (
        await load_source(database_context, source.id)
    ).last_successful_sync_at

    async def fail(
        self: FirstAbsenceDetectionService,
        pipeline_run_id: UUID,
        *,
        processed_run: PresenceRun | None = None,
        session: AsyncSession | None = None,
    ) -> FirstAbsenceDetectionResult:
        raise SQLAlchemyError("later lifecycle stage unavailable")

    monkeypatch.setattr(FirstAbsenceDetectionService, "detect_first_absences", fail)
    with pytest.raises(SourceSyncFailedError):
        await service.sync_source(source.id)
    failed = (await load_runs(database_context, source.id))[-1]
    job, _ = await load_job_and_versions(
        database_context, source_connection_id=source.id, external_job_id="1001"
    )
    assert failed.status == "failed"
    assert job.lifecycle_status == "observed" and job.consecutive_absent_runs == 1
    assert job.no_longer_observed_at is None
    events = await events_for_job(database_context, job.id)
    assert [event.event_type for event in events] == ["absence_detected"]
    assert all(event.pipeline_run_id != failed.id for event in events)
    assert (
        await load_source(database_context, source.id)
    ).last_successful_sync_at == prior_success
