from collections.abc import Sequence
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.jobs.absence_confirmation import AbsenceConfirmationService
from app.jobs.first_absence import FirstAbsenceDetectionService
from app.jobs.lifecycle_errors import (
    PresenceDataInvariantError,
    PresenceReconciliationNotAllowedError,
    PresenceReconciliationUnsafeError,
)
from app.jobs.lifecycle_repository import JobLifecycleRepository
from app.jobs.models import Job, JobLifecycleEvent, JobLifecycleStatus
from app.jobs.present_reconciliation import PresentJobReconciliationService
from app.jobs.service import NewJobPersistenceService, PersistNewJobCommand
from app.pipeline_runs.errors import PipelineRunNotFoundError
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from tests.database_counts import capture_table_counts
from tests.integration.lifecycle.helpers import (
    CONFIRMED_AT,
    FIRST_ABSENCE_AT,
    FIRST_SEEN_AT,
    RETRIEVED_AT,
    create_lifecycle_job,
    create_presence_run,
    lifecycle_state,
    load_lifecycle_events,
)
from tests.test_changed_job_persistence import (
    DatabaseContext,
    create_source,
    fixture_job,
    immutable_version_state,
    load_job,
    load_versions,
)


@pytest.mark.asyncio
async def test_second_safe_absence_confirms_with_provenance_and_preserves_content(
    database_context: DatabaseContext,
) -> None:
    initial = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        retrieved_at=FIRST_SEEN_AT,
        status=PipelineRunStatus.RUNNING,
    )
    persisted = await NewJobPersistenceService(
        database_context.session_factory
    ).create_new_job(
        PersistNewJobCommand(initial.observations[0].id, fixture_job("jobs_v1.json"))
    )
    original_version = (
        await load_versions(database_context.session_factory, persisted.job_id)
    )[0]
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, persisted.job_id)
        assert job is not None
        job.reappeared_at = FIRST_SEEN_AT
    first_missing = await create_presence_run(
        database_context, source=initial.source, retrieved_at=FIRST_ABSENCE_AT
    )
    await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(first_missing.run.id)
    current = await create_presence_run(database_context, source=initial.source)
    before_counts = await capture_table_counts(database_context.connection)

    result = await AbsenceConfirmationService(
        database_context.session_factory
    ).confirm_absences(current.run.id)

    assert result.pipeline_run_id == current.run.id
    assert result.source_connection_id == current.source.id
    assert result.evaluated_jobs == result.confirmed_not_observed == 1
    assert result.skipped_present == result.skipped_already_applied == 0
    stored = await load_job(database_context.session_factory, persisted.job_id)
    assert stored.lifecycle_status == "not_observed"
    assert stored.consecutive_absent_runs == 2
    assert stored.absence_first_detected_at == FIRST_ABSENCE_AT
    assert stored.first_seen_at == stored.last_seen_at == FIRST_SEEN_AT
    assert stored.reappeared_at == FIRST_SEEN_AT
    events = await load_lifecycle_events(database_context, current.run.id)
    assert len(events) == 1
    event = events[0]
    assert event.job_id == persisted.job_id
    assert event.pipeline_run_id == current.run.id
    assert event.event_type == "not_observed_confirmed"
    assert event.previous_status == "observed"
    assert event.new_status == "not_observed"
    assert (
        event.occurred_at
        == stored.no_longer_observed_at
        == current.snapshot.retrieved_at
        == RETRIEVED_AT
    )
    assert event.occurred_at != current.run.completed_at
    assert event.event_metadata == {
        "consecutive_absent_runs": 2,
        "confirmation_threshold": 2,
    }
    assert len(await load_lifecycle_events(database_context, first_missing.run.id)) == 1
    versions = await load_versions(database_context.session_factory, persisted.job_id)
    assert len(versions) == 1
    assert immutable_version_state(versions[0]) == immutable_version_state(
        original_version
    )
    after_counts = await capture_table_counts(database_context.connection)
    for table, count in before_counts.items():
        assert after_counts[table] == count + (table == "job_lifecycle_events")
    async with database_context.session_factory() as session:
        run = await session.get(PipelineRun, current.run.id)
        assert run is not None
        for field in (
            "status",
            "completed_at",
            "records_fetched",
            "records_valid",
            "records_quarantined",
            "jobs_new",
            "jobs_changed",
            "jobs_unchanged",
        ):
            assert getattr(run, field) == getattr(current.run, field)


@pytest.mark.asyncio
@pytest.mark.parametrize("evidence", ["valid", "quarantine", "overlap"])
async def test_present_ids_are_unchanged_while_missing_job_confirms_in_safe_run(
    database_context: DatabaseContext, evidence: str
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")] if evidence != "quarantine" else [],
        quarantines=[("1001", "jobs[0]")] if evidence != "valid" else [],
        records_valid=1 if evidence == "valid" else 0,
    )
    present = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    missing = await create_lifecycle_job(
        database_context,
        setup.source,
        "1002",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )

    result = await AbsenceConfirmationService(
        database_context.session_factory
    ).confirm_absences(setup.run.id)

    assert result.evaluated_jobs == 2
    assert result.skipped_present == result.confirmed_not_observed == 1
    stored_present = await load_job(database_context.session_factory, present.id)
    assert lifecycle_state(stored_present) == lifecycle_state(present)
    assert stored_present.updated_at == present.updated_at
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert [event.job_id for event in events] == [missing.id]


@pytest.mark.asyncio
async def test_safe_empty_board_confirms_only_eligible_source_jobs(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)
    candidates = [
        await create_lifecycle_job(
            database_context,
            setup.source,
            external_id,
            absence_count=1,
            absence_first_at=FIRST_ABSENCE_AT,
        )
        for external_id in ("1001", "1002")
    ]
    zero_count = await create_lifecycle_job(database_context, setup.source, "1003")
    confirmed = await create_lifecycle_job(
        database_context,
        setup.source,
        "1004",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )
    other_source = await create_source(database_context.session_factory)
    other_job = await create_lifecycle_job(
        database_context,
        other_source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )

    result = await AbsenceConfirmationService(
        database_context.session_factory
    ).confirm_absences(setup.run.id)

    assert result.evaluated_jobs == result.confirmed_not_observed == 2
    for candidate in candidates:
        stored = await load_job(database_context.session_factory, candidate.id)
        assert stored.lifecycle_status == "not_observed"
        assert stored.consecutive_absent_runs == 2
    for unchanged in (zero_count, confirmed, other_job):
        assert lifecycle_state(
            await load_job(database_context.session_factory, unchanged.id)
        ) == lifecycle_state(unchanged)
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert len(events) == 2
    assert {event.job_id for event in events} == {job.id for job in candidates}


@pytest.mark.asyncio
async def test_unsafe_presence_causes_zero_mutation(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context, quarantines=[(None, "jobs[0]")])
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    before_counts = await capture_table_counts(database_context.connection)

    with pytest.raises(
        PresenceReconciliationUnsafeError, match="unidentified_quarantine_records"
    ):
        await AbsenceConfirmationService(
            database_context.session_factory
        ).confirm_absences(setup.run.id)

    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)
    assert await capture_table_counts(database_context.connection) == before_counts
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [PipelineRunStatus.PENDING, PipelineRunStatus.RUNNING, PipelineRunStatus.FAILED],
)
async def test_unfinished_or_failed_run_cannot_confirm_absence(
    database_context: DatabaseContext, status: PipelineRunStatus
) -> None:
    setup = await create_presence_run(database_context, status=status)
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )

    with pytest.raises(PresenceReconciliationNotAllowedError):
        await AbsenceConfirmationService(
            database_context.session_factory
        ).confirm_absences(setup.run.id)

    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
async def test_missing_run_is_rejected(database_context: DatabaseContext) -> None:
    with pytest.raises(PipelineRunNotFoundError):
        await AbsenceConfirmationService(
            database_context.session_factory
        ).confirm_absences(uuid4())


@pytest.mark.asyncio
async def test_duplicate_confirmation_is_a_noop(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    service = AbsenceConfirmationService(database_context.session_factory)

    first = await service.confirm_absences(setup.run.id)
    confirmed = await load_job(database_context.session_factory, job.id)
    second = await service.confirm_absences(setup.run.id)

    assert first.confirmed_not_observed == 1
    assert second.evaluated_jobs == second.confirmed_not_observed == 0
    stored = await load_job(database_context.session_factory, job.id)
    assert lifecycle_state(stored) == lifecycle_state(confirmed)
    assert stored.updated_at == confirmed.updated_at
    assert len(await load_lifecycle_events(database_context, setup.run.id)) == 1


@pytest.mark.asyncio
async def test_task_28_and_29_cannot_count_same_run_twice_for_a_job(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)
    first_absent = await create_lifecycle_job(database_context, setup.source, "1001")
    already_absent = await create_lifecycle_job(
        database_context,
        setup.source,
        "1002",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)
    service = AbsenceConfirmationService(database_context.session_factory)

    result = await service.confirm_absences(setup.run.id)
    repeated = await service.confirm_absences(setup.run.id)

    assert result.evaluated_jobs == 2
    assert result.confirmed_not_observed == result.skipped_already_applied == 1
    assert repeated.confirmed_not_observed == 0
    assert repeated.skipped_already_applied == 1
    tentative = await load_job(database_context.session_factory, first_absent.id)
    assert tentative.lifecycle_status == "observed"
    assert tentative.consecutive_absent_runs == 1
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert {(event.job_id, event.event_type) for event in events} == {
        (first_absent.id, "absence_detected"),
        (already_absent.id, "not_observed_confirmed"),
    }


@pytest.mark.asyncio
async def test_confirmation_event_failure_rolls_back_entire_batch_and_retry_succeeds(
    database_context: DatabaseContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = await create_presence_run(database_context)
    jobs = [
        await create_lifecycle_job(
            database_context,
            setup.source,
            external_id,
            absence_count=1,
            absence_first_at=FIRST_ABSENCE_AT,
        )
        for external_id in ("1001", "1002")
    ]
    original_add = JobLifecycleRepository.add_lifecycle_events

    async def insert_then_fail(
        repository: JobLifecycleRepository, events: Sequence[JobLifecycleEvent]
    ) -> None:
        assert len(events) == 2
        await original_add(repository, events[:1])
        assert events[0].id is not None
        assert events[0].created_at is not None
        events[1].job_id = events[0].job_id
        await original_add(repository, events[1:])

    monkeypatch.setattr(
        JobLifecycleRepository, "add_lifecycle_events", insert_then_fail
    )
    with pytest.raises(IntegrityError, match="uq_job_lifecycle_events_job_run_type"):
        await AbsenceConfirmationService(
            database_context.session_factory
        ).confirm_absences(setup.run.id)

    for job in jobs:
        assert lifecycle_state(
            await load_job(database_context.session_factory, job.id)
        ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []
    monkeypatch.setattr(JobLifecycleRepository, "add_lifecycle_events", original_add)
    result = await AbsenceConfirmationService(
        database_context.session_factory
    ).confirm_absences(setup.run.id)
    assert result.confirmed_not_observed == 2
    assert len(await load_lifecycle_events(database_context, setup.run.id)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem",
    [
        "missing_timestamp",
        "excess_count",
        "equal_time",
        "older_time",
        "newer_freshness",
    ],
)
async def test_inconsistent_or_stale_absence_state_fails_without_mutation(
    database_context: DatabaseContext, problem: str
) -> None:
    first_absence_at = {
        "equal_time": RETRIEVED_AT,
        "older_time": RETRIEVED_AT + timedelta(days=1),
    }.get(problem, FIRST_ABSENCE_AT)
    setup = await create_presence_run(database_context)
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=2 if problem == "excess_count" else 1,
        absence_first_at=None if problem == "missing_timestamp" else first_absence_at,
    )
    if problem == "newer_freshness":
        async with database_context.session_factory.begin() as session:
            stored = await session.get(Job, job.id)
            assert stored is not None
            stored.last_seen_at = RETRIEVED_AT + timedelta(days=1)
    before = await load_job(database_context.session_factory, job.id)

    with pytest.raises(PresenceDataInvariantError):
        await AbsenceConfirmationService(
            database_context.session_factory
        ).confirm_absences(setup.run.id)

    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(before)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
async def test_old_confirmation_run_cannot_count_toward_a_later_absence_cycle(
    database_context: DatabaseContext,
) -> None:
    initial = await create_presence_run(database_context)
    job = await create_lifecycle_job(
        database_context,
        initial.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    service = AbsenceConfirmationService(database_context.session_factory)
    await service.confirm_absences(initial.run.id)
    present = await create_presence_run(
        database_context,
        source=initial.source,
        observations=[("1001", "jobs[0]")],
        retrieved_at=RETRIEVED_AT + timedelta(days=1),
    )
    await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(present.run.id)
    first_missing = await create_presence_run(
        database_context,
        source=initial.source,
        retrieved_at=RETRIEVED_AT + timedelta(days=2),
    )
    await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(first_missing.run.id)
    before = await load_job(database_context.session_factory, job.id)

    replay = await service.confirm_absences(initial.run.id)

    assert replay.confirmed_not_observed == 0
    assert replay.skipped_already_applied == 1
    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(before)
    assert len(await load_lifecycle_events(database_context, initial.run.id)) == 1
    second_missing = await create_presence_run(
        database_context,
        source=initial.source,
        retrieved_at=RETRIEVED_AT + timedelta(days=3),
    )
    confirmed = await service.confirm_absences(second_missing.run.id)
    assert confirmed.confirmed_not_observed == 1
    stored = await load_job(database_context.session_factory, job.id)
    assert stored.absence_first_detected_at == first_missing.snapshot.retrieved_at
    assert stored.no_longer_observed_at == second_missing.snapshot.retrieved_at
    assert stored.reappeared_at == present.snapshot.retrieved_at
