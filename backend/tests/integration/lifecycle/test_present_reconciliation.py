from collections.abc import Sequence
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.jobs.lifecycle_errors import (
    PresenceDataInvariantError,
    PresenceReconciliationNotAllowedError,
    PresenceReconciliationUnsafeError,
)
from app.jobs.lifecycle_repository import JobLifecycleRepository
from app.jobs.models import Job, JobChangeEvent, JobLifecycleEvent, JobLifecycleStatus
from app.jobs.present_reconciliation import PresentJobReconciliationService
from app.jobs.service import (
    ApplyChangedObservationCommand,
    ApplyUnchangedObservationCommand,
    ChangedJobPersistenceService,
    NewJobPersistenceService,
    PersistNewJobCommand,
    UnchangedJobPersistenceService,
)
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
@pytest.mark.parametrize(
    "initial_status,absence_count,evidence,expected_action",
    [
        (JobLifecycleStatus.OBSERVED, 0, "valid", "none"),
        (JobLifecycleStatus.OBSERVED, 0, "quarantine", "none"),
        (JobLifecycleStatus.OBSERVED, 1, "valid", "reset"),
        (JobLifecycleStatus.OBSERVED, 1, "quarantine", "reset"),
        (JobLifecycleStatus.NOT_OBSERVED, 2, "valid", "reappear"),
        (JobLifecycleStatus.NOT_OBSERVED, 2, "quarantine", "none"),
    ],
)
async def test_presence_evidence_and_lifecycle_case_matrix(
    database_context: DatabaseContext,
    initial_status: JobLifecycleStatus,
    absence_count: int,
    evidence: str,
    expected_action: str,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")] if evidence == "valid" else [],
        quarantines=[("1001", "jobs[0]")] if evidence == "quarantine" else [],
    )
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        status=initial_status,
        absence_count=absence_count,
        absence_first_at=FIRST_ABSENCE_AT if absence_count else None,
        confirmed_at=CONFIRMED_AT
        if initial_status is JobLifecycleStatus.NOT_OBSERVED
        else None,
    )
    original_state = lifecycle_state(job)
    before_counts = await capture_table_counts(database_context.connection)

    result = await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(setup.run.id)

    stored = await load_job(database_context.session_factory, job.id)
    events = await load_lifecycle_events(database_context, setup.run.id)
    assert result.pipeline_run_id == setup.run.id
    assert result.source_connection_id == setup.source.id
    assert result.evaluated_present_jobs == 1
    assert result.tentative_absences_reset == (1 if expected_action == "reset" else 0)
    assert result.jobs_reappeared == (1 if expected_action == "reappear" else 0)
    if expected_action == "none":
        assert lifecycle_state(stored) == original_state
        assert events == []
    else:
        assert stored.lifecycle_status == JobLifecycleStatus.OBSERVED.value
        assert stored.consecutive_absent_runs == 0
        assert stored.absence_first_detected_at is None
        assert stored.first_seen_at == stored.last_seen_at == FIRST_SEEN_AT
        assert stored.no_longer_observed_at == job.no_longer_observed_at
        if expected_action == "reset":
            assert stored.reappeared_at is None
            assert events == []
        else:
            assert stored.reappeared_at == RETRIEVED_AT
            assert len(events) == 1
            event = events[0]
            assert event.event_type == "reappeared"
            assert event.job_id == job.id
            assert event.pipeline_run_id == setup.run.id
            assert event.previous_status == "not_observed"
            assert event.new_status == "observed"
            assert (
                event.occurred_at == stored.reappeared_at == setup.snapshot.retrieved_at
            )
            assert event.event_metadata == {
                "previous_consecutive_absent_runs": 2,
                "previous_no_longer_observed_at": CONFIRMED_AT.isoformat(),
            }
    after_counts = await capture_table_counts(database_context.connection)
    for table in before_counts:
        expected_count = before_counts[table] + (
            1
            if table == "job_lifecycle_events" and expected_action == "reappear"
            else 0
        )
        assert after_counts[table] == expected_count


@pytest.mark.asyncio
async def test_post_validation_quarantine_observation_cannot_confirm_reappearance(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        quarantines=[("1001", "jobs[0]")],
        records_valid=0,
    )
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )

    result = await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(setup.run.id)

    assert result.quarantine_presence_only == 1
    assert result.jobs_reappeared == 0
    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
async def test_valid_record_with_quarantined_duplicate_can_reappear(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        quarantines=[("1001", "jobs[1]")],
    )
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )

    result = await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(setup.run.id)

    assert result.jobs_reappeared == 1
    assert result.quarantine_presence_only == 0
    assert (
        await load_job(database_context.session_factory, job.id)
    ).lifecycle_status == "observed"


@pytest.mark.asyncio
async def test_absent_jobs_and_other_sources_are_unchanged(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context, observations=[("1001", "jobs[0]")]
    )
    other_source = await create_source(database_context.session_factory)
    present_job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    absent_job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1002",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    other_job = await create_lifecycle_job(
        database_context,
        other_source,
        "1001",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )

    result = await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(setup.run.id)

    assert result.evaluated_present_jobs == result.tentative_absences_reset == 1
    assert (
        await load_job(database_context.session_factory, present_job.id)
    ).consecutive_absent_runs == 0
    for unchanged in (absent_job, other_job):
        assert lifecycle_state(
            await load_job(database_context.session_factory, unchanged.id)
        ) == lifecycle_state(unchanged)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
async def test_unsafe_run_causes_zero_mutation_for_all_present_jobs(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]"), ("1002", "jobs[1]")],
        quarantines=[(None, "jobs[2]")],
    )
    tentative = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    confirmed = await create_lifecycle_job(
        database_context,
        setup.source,
        "1002",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )

    with pytest.raises(
        PresenceReconciliationUnsafeError, match="unidentified_quarantine_records"
    ):
        await PresentJobReconciliationService(
            database_context.session_factory
        ).reconcile_present_jobs(setup.run.id)

    for unchanged in (tentative, confirmed):
        assert lifecycle_state(
            await load_job(database_context.session_factory, unchanged.id)
        ) == lifecycle_state(unchanged)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [PipelineRunStatus.PENDING, PipelineRunStatus.RUNNING, PipelineRunStatus.FAILED],
)
async def test_unfinished_or_failed_runs_are_rejected_before_mutation(
    database_context: DatabaseContext,
    status: PipelineRunStatus,
) -> None:
    setup = await create_presence_run(
        database_context, observations=[("1001", "jobs[0]")], status=status
    )
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )

    with pytest.raises(PresenceReconciliationNotAllowedError):
        await PresentJobReconciliationService(
            database_context.session_factory
        ).reconcile_present_jobs(setup.run.id)

    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)


@pytest.mark.asyncio
async def test_safe_empty_board_does_not_mutate_jobs(
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

    result = await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(setup.run.id)

    assert (
        result.evaluated_present_jobs
        == result.tentative_absences_reset
        == result.jobs_reappeared
        == 0
    )
    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)


@pytest.mark.asyncio
async def test_repeated_invocation_is_a_noop(database_context: DatabaseContext) -> None:
    setup = await create_presence_run(
        database_context, observations=[("1001", "jobs[0]")]
    )
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )
    service = PresentJobReconciliationService(database_context.session_factory)

    first = await service.reconcile_present_jobs(setup.run.id)
    first_state = lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    )
    second = await service.reconcile_present_jobs(setup.run.id)

    assert first.jobs_reappeared == 1
    assert second.jobs_reappeared == second.tentative_absences_reset == 0
    assert (
        lifecycle_state(await load_job(database_context.session_factory, job.id))
        == first_state
    )
    assert len(await load_lifecycle_events(database_context, setup.run.id)) == 1


@pytest.mark.asyncio
async def test_event_insert_failure_rolls_back_reappearance_and_tentative_reset(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await create_presence_run(
        database_context, observations=[("1001", "jobs[0]"), ("1002", "jobs[1]")]
    )
    confirmed = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        status=JobLifecycleStatus.NOT_OBSERVED,
        absence_count=2,
        absence_first_at=FIRST_ABSENCE_AT,
        confirmed_at=CONFIRMED_AT,
    )
    tentative = await create_lifecycle_job(
        database_context,
        setup.source,
        "1002",
        absence_count=1,
        absence_first_at=FIRST_ABSENCE_AT,
    )
    original_add = JobLifecycleRepository.add_lifecycle_events

    async def insert_then_fail(
        repository: JobLifecycleRepository, events: Sequence[JobLifecycleEvent]
    ) -> None:
        assert len(events) == 1
        await original_add(repository, events)
        event = events[0]
        assert event.id is not None
        assert event.created_at is not None
        await original_add(
            repository,
            [
                JobLifecycleEvent(
                    job_id=event.job_id,
                    pipeline_run_id=event.pipeline_run_id,
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    previous_status=event.previous_status,
                    new_status=event.new_status,
                )
            ],
        )

    monkeypatch.setattr(
        JobLifecycleRepository, "add_lifecycle_events", insert_then_fail
    )
    with pytest.raises(IntegrityError, match="uq_job_lifecycle_events_job_run_type"):
        await PresentJobReconciliationService(
            database_context.session_factory
        ).reconcile_present_jobs(setup.run.id)

    for unchanged in (confirmed, tentative):
        assert lifecycle_state(
            await load_job(database_context.session_factory, unchanged.id)
        ) == lifecycle_state(unchanged)
    assert await load_lifecycle_events(database_context, setup.run.id) == []
    monkeypatch.setattr(JobLifecycleRepository, "add_lifecycle_events", original_add)
    retry = await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(setup.run.id)
    assert retry.jobs_reappeared == retry.tentative_absences_reset == 1


@pytest.mark.asyncio
async def test_old_presence_cannot_clear_more_recent_absence_state(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context, observations=[("1001", "jobs[0]")]
    )
    job = await create_lifecycle_job(
        database_context,
        setup.source,
        "1001",
        absence_count=1,
        absence_first_at=RETRIEVED_AT + timedelta(days=1),
    )

    with pytest.raises(PresenceDataInvariantError, match="predates"):
        await PresentJobReconciliationService(
            database_context.session_factory
        ).reconcile_present_jobs(setup.run.id)

    assert lifecycle_state(
        await load_job(database_context.session_factory, job.id)
    ) == lifecycle_state(job)
    assert await load_lifecycle_events(database_context, setup.run.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_reappearance_composes_with_existing_content_processing(
    database_context: DatabaseContext,
    changed: bool,
) -> None:
    initial = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        retrieved_at=FIRST_SEEN_AT,
        status=PipelineRunStatus.RUNNING,
    )
    original_record = fixture_job("jobs_v1.json")
    first = await NewJobPersistenceService(
        database_context.session_factory
    ).create_new_job(PersistNewJobCommand(initial.observations[0].id, original_record))
    original_version = (
        await load_versions(database_context.session_factory, first.job_id)
    )[0]
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, first.job_id)
        assert job is not None
        job.lifecycle_status = "not_observed"
        job.consecutive_absent_runs = 2
        job.absence_first_detected_at = FIRST_ABSENCE_AT
        job.no_longer_observed_at = CONFIRMED_AT

    current = await create_presence_run(
        database_context,
        source=initial.source,
        observations=[("1001", "jobs[0]")],
        status=PipelineRunStatus.RUNNING,
    )
    if changed:
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(
                current.observations[0].id, fixture_job("jobs_v2.json")
            )
        )
    else:
        await UnchangedJobPersistenceService(
            database_context.session_factory
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(
                current.observations[0].id, original_record
            )
        )
    async with database_context.session_factory.begin() as session:
        run = await session.get(PipelineRun, current.run.id)
        assert run is not None
        run.status = PipelineRunStatus.COMPLETED.value
        run.completed_at = RETRIEVED_AT + timedelta(hours=1)
        run.jobs_new = 0
        run.jobs_changed = int(changed)
        run.jobs_unchanged = int(not changed)

    counts_before = await capture_table_counts(database_context.connection)
    result = await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(current.run.id)

    assert result.jobs_reappeared == 1
    stored = await load_job(database_context.session_factory, first.job_id)
    assert stored.last_seen_at == RETRIEVED_AT
    assert stored.first_seen_at == FIRST_SEEN_AT
    assert stored.lifecycle_status == "observed"
    assert stored.no_longer_observed_at == CONFIRMED_AT
    assert stored.reappeared_at == RETRIEVED_AT
    versions = await load_versions(database_context.session_factory, first.job_id)
    assert len(versions) == (2 if changed else 1)
    assert immutable_version_state(versions[0]) == immutable_version_state(
        original_version
    )
    async with database_context.session_factory() as session:
        changes = list(
            await session.scalars(
                select(JobChangeEvent).where(JobChangeEvent.job_id == first.job_id)
            )
        )
    assert bool(changes) is changed
    assert len(await load_lifecycle_events(database_context, current.run.id)) == 1
    counts_after = await capture_table_counts(database_context.connection)
    assert counts_after["job_versions"] == counts_before["job_versions"]
    assert counts_after["job_change_events"] == counts_before["job_change_events"]
