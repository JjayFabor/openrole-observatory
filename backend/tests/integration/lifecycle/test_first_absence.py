from collections.abc import Sequence
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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
async def test_first_absence_preserves_content_and_freshness_with_event_provenance(
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
    # A job can have historical removal/reappearance timestamps after returning.
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, persisted.job_id)
        assert job is not None
        job.no_longer_observed_at = FIRST_ABSENCE_AT
        job.reappeared_at = CONFIRMED_AT
    setup = await create_presence_run(database_context, source=initial.source)
    before_counts = await capture_table_counts(database_context.connection)

    result = await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)

    assert result.pipeline_run_id == setup.run.id
    assert result.source_connection_id == setup.source.id
    assert result.evaluated_jobs == result.first_absences_detected == 1
    assert result.skipped_already_absent == 0
    stored = await load_job(database_context.session_factory, persisted.job_id)
    assert stored.consecutive_absent_runs == 1
    assert stored.lifecycle_status == "observed"
    assert stored.first_seen_at == stored.last_seen_at == FIRST_SEEN_AT
    assert stored.no_longer_observed_at == FIRST_ABSENCE_AT
    assert stored.reappeared_at == CONFIRMED_AT
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert len(events) == 1
    event = events[0]
    assert event.job_id == persisted.job_id
    assert event.pipeline_run_id == setup.run.id
    assert event.event_type == "absence_detected"
    assert event.previous_status == event.new_status == "observed"
    assert (
        event.occurred_at
        == stored.absence_first_detected_at
        == setup.snapshot.retrieved_at
        == RETRIEVED_AT
    )
    assert event.occurred_at != setup.run.completed_at
    assert event.event_metadata == {"consecutive_absent_runs": 1}
    versions = await load_versions(database_context.session_factory, persisted.job_id)
    assert len(versions) == 1
    assert immutable_version_state(versions[0]) == immutable_version_state(
        original_version
    )
    after_counts = await capture_table_counts(database_context.connection)
    for table, count in before_counts.items():
        assert after_counts[table] == count + (table == "job_lifecycle_events")
    async with database_context.session_factory() as session:
        run = await session.get(PipelineRun, setup.run.id)
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
            assert getattr(run, field) == getattr(setup.run, field)


@pytest.mark.asyncio
@pytest.mark.parametrize("absence_count", [0, 1])
async def test_present_jobs_are_unchanged_even_with_tentative_absence(
    database_context: DatabaseContext, absence_count: int
) -> None:
    setup = await create_presence_run(
        database_context, observations=[("1001", "jobs[0]")]
    )
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=absence_count,
        absence_first_at=FIRST_ABSENCE_AT if absence_count else None,
    )

    result = await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)

    assert result.evaluated_jobs == 1
    assert result.first_absences_detected == result.skipped_already_absent == 0
    stored = await load_job(database_context.session_factory, job.id)
    assert lifecycle_state(stored) == lifecycle_state(job)
    assert stored.updated_at == job.updated_at
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("absence_count", [1, 3])
async def test_missing_jobs_with_existing_absence_are_not_advanced(
    database_context: DatabaseContext, absence_count: int
) -> None:
    setup = await create_presence_run(database_context)
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=absence_count,
        absence_first_at=FIRST_ABSENCE_AT,
    )

    result = await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)

    assert result.evaluated_jobs == result.skipped_already_absent == 1
    assert result.first_absences_detected == 0
    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
async def test_other_sources_and_not_observed_jobs_are_excluded(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)
    candidate = await create_lifecycle_job(database_context, setup.source, "1001")
    confirmed = await create_lifecycle_job(
        database_context,
        setup.source,
        "1002",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )
    other_source = await create_source(database_context.session_factory)
    other_job = await create_lifecycle_job(database_context, other_source, "1001")

    result = await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)

    assert result.evaluated_jobs == result.first_absences_detected == 1
    for unchanged in (confirmed, other_job):
        assert lifecycle_state(
            await load_job(database_context.session_factory, unchanged.id)
        ) == lifecycle_state(unchanged)
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert [event.job_id for event in events] == [candidate.id]


@pytest.mark.asyncio
async def test_unidentified_quarantine_blocks_all_absence_mutations(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        quarantines=[(None, "jobs[1]")],
    )
    jobs = [
        await create_lifecycle_job(database_context, setup.source, external_id)
        for external_id in ("1001", "1002")
    ]
    before_counts = await capture_table_counts(database_context.connection)

    with pytest.raises(
        PresenceReconciliationUnsafeError, match="unidentified_quarantine_records"
    ):
        await FirstAbsenceDetectionService(
            database_context.session_factory
        ).detect_first_absences(setup.run.id)

    for job in jobs:
        assert lifecycle_state(
            await load_job(database_context.session_factory, job.id)
        ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []
    assert await capture_table_counts(database_context.connection) == before_counts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [PipelineRunStatus.PENDING, PipelineRunStatus.RUNNING, PipelineRunStatus.FAILED],
)
async def test_unfinished_or_failed_run_is_rejected(
    database_context: DatabaseContext, status: PipelineRunStatus
) -> None:
    setup = await create_presence_run(database_context, status=status)
    job = await create_lifecycle_job(database_context, setup.source, "1001")

    with pytest.raises(PresenceReconciliationNotAllowedError):
        await FirstAbsenceDetectionService(
            database_context.session_factory
        ).detect_first_absences(setup.run.id)

    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
async def test_missing_run_is_rejected(database_context: DatabaseContext) -> None:
    with pytest.raises(PipelineRunNotFoundError):
        await FirstAbsenceDetectionService(
            database_context.session_factory
        ).detect_first_absences(uuid4())


@pytest.mark.asyncio
async def test_safe_empty_board_detects_all_first_absences(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)
    jobs = [
        await create_lifecycle_job(database_context, setup.source, external_id)
        for external_id in ("1001", "1002", "1003")
    ]

    result = await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)

    assert result.evaluated_jobs == result.first_absences_detected == 3
    for job in jobs:
        stored = await load_job(database_context.session_factory, job.id)
        assert stored.consecutive_absent_runs == 1
        assert stored.lifecycle_status == "observed"
        assert stored.absence_first_detected_at == RETRIEVED_AT
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert {event.job_id for event in events} == {job.id for job in jobs}
    assert len(events) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("overlapping_observation", [False, True])
async def test_recoverable_quarantine_prevents_false_absence_in_safe_partial_run(
    database_context: DatabaseContext, overlapping_observation: bool
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")] if overlapping_observation else [],
        quarantines=[("1001", "jobs[0]")],
        records_valid=0,
    )
    present = await create_lifecycle_job(database_context, setup.source, "1001")
    missing = await create_lifecycle_job(database_context, setup.source, "1002")

    result = await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)

    assert setup.run.status == "completed_with_errors"
    assert result.evaluated_jobs == 2
    assert result.first_absences_detected == 1
    assert lifecycle_state(
        await load_job(database_context.session_factory, present.id)
    ) == lifecycle_state(present)
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert [event.job_id for event in events] == [missing.id]


@pytest.mark.asyncio
async def test_repeated_invocation_and_later_missing_run_do_not_advance_count(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)
    job = await create_lifecycle_job(database_context, setup.source, "1001")
    service = FirstAbsenceDetectionService(database_context.session_factory)

    first = await service.detect_first_absences(setup.run.id)
    first_state = lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    )
    duplicate = await service.detect_first_absences(setup.run.id)
    later = await create_presence_run(
        database_context,
        source=setup.source,
        retrieved_at=RETRIEVED_AT + timedelta(days=1),
    )
    subsequent = await service.detect_first_absences(later.run.id)

    assert first.first_absences_detected == 1
    for skipped in (duplicate, subsequent):
        assert skipped.first_absences_detected == 0
        assert skipped.skipped_already_absent == 1
    assert (
        lifecycle_state(await load_job(database_context.session_factory, job.id))
        == first_state
    )
    assert len(await load_lifecycle_events(database_context, setup.run.id)) == 1
    assert await load_lifecycle_events(database_context, later.run.id) == []


@pytest.mark.asyncio
async def test_event_insert_failure_rolls_back_entire_batch_then_retry_succeeds(
    database_context: DatabaseContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = await create_presence_run(database_context)
    jobs = [
        await create_lifecycle_job(database_context, setup.source, external_id)
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
        await FirstAbsenceDetectionService(
            database_context.session_factory
        ).detect_first_absences(setup.run.id)

    for job in jobs:
        assert lifecycle_state(
            await load_job(database_context.session_factory, job.id)
        ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []
    monkeypatch.setattr(JobLifecycleRepository, "add_lifecycle_events", original_add)
    retry = await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(setup.run.id)
    assert retry.first_absences_detected == 2
    assert len(await load_lifecycle_events(database_context, setup.run.id)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["existing_timestamp", "newer_last_seen"])
async def test_inconsistent_or_stale_evidence_is_rejected_without_mutation(
    database_context: DatabaseContext, problem: str
) -> None:
    setup = await create_presence_run(database_context)
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_first_at=FIRST_ABSENCE_AT if problem == "existing_timestamp" else None,
    )
    if problem == "newer_last_seen":
        async with database_context.session_factory.begin() as session:
            stored = await session.get(Job, job.id)
            assert stored is not None
            stored.last_seen_at = RETRIEVED_AT + timedelta(days=1)
    before = await load_job(database_context.session_factory, job.id)

    with pytest.raises(
        PresenceDataInvariantError,
        match="first-absence timestamp"
        if problem == "existing_timestamp"
        else "predates",
    ):
        await FirstAbsenceDetectionService(
            database_context.session_factory
        ).detect_first_absences(setup.run.id)

    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(before)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
async def test_old_run_replay_after_reset_is_rejected_and_new_cycle_is_allowed(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)
    job = await create_lifecycle_job(database_context, setup.source, "1001")
    service = FirstAbsenceDetectionService(database_context.session_factory)
    await service.detect_first_absences(setup.run.id)
    present = await create_presence_run(
        database_context,
        source=setup.source,
        quarantines=[("1001", "jobs[0]")],
        retrieved_at=RETRIEVED_AT + timedelta(days=1),
    )
    await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(present.run.id)
    reset_state = lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    )

    with pytest.raises(IntegrityError, match="uq_job_lifecycle_events_job_run_type"):
        await service.detect_first_absences(setup.run.id)

    assert (
        lifecycle_state(await load_job(database_context.session_factory, job.id))
        == reset_state
    )
    assert len(await load_lifecycle_events(database_context, setup.run.id)) == 1
    next_absence = await create_presence_run(
        database_context,
        source=setup.source,
        retrieved_at=RETRIEVED_AT + timedelta(days=2),
    )
    result = await service.detect_first_absences(next_absence.run.id)
    assert result.first_absences_detected == 1
    stored = await load_job(database_context.session_factory, job.id)
    assert stored.absence_first_detected_at == next_absence.snapshot.retrieved_at
    assert len(await load_lifecycle_events(database_context, next_absence.run.id)) == 1
