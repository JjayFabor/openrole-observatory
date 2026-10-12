from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import JsonValue
from sqlalchemy import JSON, delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.jobs.models import (
    FieldChangeType,
    Job,
    JobChangeEvent,
    JobLifecycleEvent,
    JobLifecycleEventType,
    JobLifecycleStatus,
    JobVersion,
)
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from tests.test_jobs import OBSERVED_AT, build_version, create_job, create_observation

TRANSITION_AT = OBSERVED_AT + timedelta(days=1)


async def create_versions(
    session: AsyncSession,
) -> tuple[Job, JobVersion, JobVersion]:
    job = await create_job(session, key=f"events-{uuid4().hex}")
    first_observation = await create_observation(session, job)
    second_observation = await create_observation(
        session, job, observed_at=TRANSITION_AT
    )
    first = build_version(
        job, first_observation, is_current=False, effective_to=TRANSITION_AT
    )
    second = build_version(
        job,
        second_observation,
        version_number=2,
        content_hash="b" * 64,
        effective_from=TRANSITION_AT,
    )
    first.workplace_type = "remote"
    second.workplace_type = "hybrid"
    session.add_all([first, second])
    await session.flush()
    return job, first, second


def change_event(
    job: Job,
    first: JobVersion,
    second: JobVersion,
    *,
    field_name: str = "workplace_type",
    old_value: JsonValue = "remote",
    new_value: JsonValue = "hybrid",
) -> JobChangeEvent:
    return JobChangeEvent(
        job_id=job.id,
        from_version_id=first.id,
        to_version_id=second.id,
        field_name=field_name,
        change_type=FieldChangeType.MODIFIED.value,
        old_value=old_value,
        new_value=new_value,
        detected_at=second.effective_from,
    )


async def create_run(session: AsyncSession, job: Job) -> PipelineRun:
    run = PipelineRun(
        source_connection_id=job.source_connection_id,
        status=PipelineRunStatus.COMPLETED.value,
        started_at=TRANSITION_AT,
        completed_at=TRANSITION_AT,
    )
    session.add(run)
    await session.flush()
    return run


def lifecycle_event(
    job: Job,
    run: PipelineRun,
    *,
    event_type: JobLifecycleEventType = JobLifecycleEventType.ABSENCE_DETECTED,
) -> JobLifecycleEvent:
    return JobLifecycleEvent(
        job_id=job.id,
        pipeline_run_id=run.id,
        event_type=event_type.value,
        occurred_at=TRANSITION_AT,
        previous_status=JobLifecycleStatus.OBSERVED.value,
        new_status=JobLifecycleStatus.OBSERVED.value,
    )


@pytest.mark.asyncio
async def test_job_absence_defaults_and_mutable_state(db_session: AsyncSession) -> None:
    job = await create_job(db_session, key=f"absence-{uuid4().hex}")
    await db_session.refresh(job)

    assert job.consecutive_absent_runs == 0
    assert job.absence_first_detected_at is None

    job.consecutive_absent_runs = 1
    job.absence_first_detected_at = TRANSITION_AT
    await db_session.flush()
    await db_session.refresh(job)

    assert job.consecutive_absent_runs == 1
    assert job.absence_first_detected_at == TRANSITION_AT
    assert job.absence_first_detected_at.tzinfo is not None
    assert job.lifecycle_status == JobLifecycleStatus.OBSERVED.value


@pytest.mark.asyncio
async def test_negative_absence_count_is_rejected(db_session: AsyncSession) -> None:
    job = await create_job(db_session, key=f"negative-{uuid4().hex}")

    with pytest.raises(
        IntegrityError, match="ck_jobs_consecutive_absent_runs_non_negative"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                update(Job).where(Job.id == job.id).values(consecutive_absent_runs=-1)
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "old_value", "new_value"),
    [
        ("workplace_type", "remote", "hybrid"),
        ("salary_min", 65000, 80000),
        ("canonical_metadata", {"offices": ["Berlin"]}, {"offices": ["Paris"]}),
        ("custom_boolean", False, True),
        ("custom_array", [1, "remote"], [2, "hybrid"]),
    ],
)
async def test_change_event_jsonb_persistence(
    db_session: AsyncSession,
    field_name: str,
    old_value: JsonValue,
    new_value: JsonValue,
) -> None:
    job, first, second = await create_versions(db_session)
    event = change_event(
        job,
        first,
        second,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
    )
    db_session.add(event)
    await db_session.flush()
    event_id, job_id, first_id, second_id = event.id, job.id, first.id, second.id
    db_session.expunge_all()

    loaded = await db_session.get(JobChangeEvent, event_id)
    assert loaded is not None
    assert isinstance(loaded.id, UUID)
    assert (loaded.job_id, loaded.from_version_id, loaded.to_version_id) == (
        job_id,
        first_id,
        second_id,
    )
    assert loaded.field_name == field_name
    assert loaded.change_type == FieldChangeType.MODIFIED.value
    assert loaded.old_value == old_value
    assert loaded.new_value == new_value
    assert type(loaded.old_value) is type(old_value)
    assert type(loaded.new_value) is type(new_value)
    assert loaded.detected_at == TRANSITION_AT
    assert loaded.detected_at.tzinfo is not None
    assert loaded.created_at.tzinfo is not None


@pytest.mark.asyncio
async def test_sql_null_and_json_null_remain_distinct(db_session: AsyncSession) -> None:
    job, first, second = await create_versions(db_session)
    added = change_event(
        job, first, second, field_name="salary_min", old_value=None, new_value=65000
    )
    added.change_type = FieldChangeType.ADDED.value
    removed = change_event(
        job, first, second, field_name="salary_max", old_value=80000, new_value=None
    )
    removed.change_type = FieldChangeType.REMOVED.value
    explicit_null = change_event(job, first, second, field_name="canonical_metadata")
    explicit_null.old_value = JSON.NULL
    explicit_null.new_value = JSON.NULL
    db_session.add_all([added, removed, explicit_null])
    await db_session.flush()

    rows = (
        (
            await db_session.execute(
                text(
                    "SELECT field_name, old_value IS NULL AS old_sql_null, "
                    "new_value IS NULL AS new_sql_null, jsonb_typeof(old_value) AS old_json_type, "
                    "jsonb_typeof(new_value) AS new_json_type "
                    "FROM job_change_events WHERE job_id = :job_id"
                ),
                {"job_id": job.id},
            )
        )
        .mappings()
        .all()
    )
    by_field = {row["field_name"]: row for row in rows}
    assert by_field["salary_min"]["old_sql_null"] is True
    assert by_field["salary_min"]["new_json_type"] == "number"
    assert by_field["salary_max"]["new_sql_null"] is True
    assert by_field["salary_max"]["old_json_type"] == "number"
    assert by_field["canonical_metadata"]["old_sql_null"] is False
    assert by_field["canonical_metadata"]["new_sql_null"] is False
    assert by_field["canonical_metadata"]["old_json_type"] == "null"
    assert by_field["canonical_metadata"]["new_json_type"] == "null"


@pytest.mark.asyncio
async def test_duplicate_change_is_rejected_but_other_fields_are_allowed(
    db_session: AsyncSession,
) -> None:
    job, first, second = await create_versions(db_session)
    db_session.add_all(
        [
            change_event(job, first, second),
            change_event(
                job,
                first,
                second,
                field_name="location_text",
                old_value="Remote",
                new_value="Berlin",
            ),
        ]
    )
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_job_change_events_from_to_field"):
        async with db_session.begin_nested():
            db_session.add(change_event(job, first, second))
            await db_session.flush()

    events = (
        await db_session.scalars(
            select(JobChangeEvent).where(JobChangeEvent.job_id == job.id)
        )
    ).all()
    assert {event.field_name for event in events} == {"workplace_type", "location_text"}


@pytest.mark.asyncio
async def test_change_relationships_navigate_both_version_roles(
    db_session: AsyncSession,
) -> None:
    job, first, second = await create_versions(db_session)
    event = change_event(job, first, second)
    db_session.add(event)
    await db_session.flush()
    event_id, job_id, first_id, second_id = event.id, job.id, first.id, second.id
    db_session.expunge_all()

    loaded_job = await db_session.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(
            selectinload(Job.change_events),
            selectinload(Job.versions).selectinload(JobVersion.outgoing_change_events),
            selectinload(Job.versions).selectinload(JobVersion.incoming_change_events),
        )
    )
    loaded_event = await db_session.scalar(
        select(JobChangeEvent)
        .where(JobChangeEvent.id == event_id)
        .options(
            joinedload(JobChangeEvent.job),
            joinedload(JobChangeEvent.from_version),
            joinedload(JobChangeEvent.to_version),
        )
    )
    assert loaded_job is not None
    assert loaded_event is not None
    assert [event.id for event in loaded_job.change_events] == [event_id]
    old, new = loaded_job.versions
    assert [event.id for event in old.outgoing_change_events] == [event_id]
    assert old.incoming_change_events == []
    assert [event.id for event in new.incoming_change_events] == [event_id]
    assert new.outgoing_change_events == []
    assert loaded_event.job.id == job_id
    assert loaded_event.from_version.id == first_id
    assert loaded_event.to_version.id == second_id


@pytest.mark.asyncio
async def test_lifecycle_persistence_metadata_and_relationships(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session, key=f"lifecycle-{uuid4().hex}")
    run = await create_run(db_session, job)
    event = lifecycle_event(job, run)
    event.event_metadata = {"consecutive_absent_runs": 1, "confirmation_threshold": 2}
    db_session.add(event)
    await db_session.flush()
    event_id, job_id, run_id = event.id, job.id, run.id
    db_session.expunge_all()

    loaded = await db_session.scalar(
        select(JobLifecycleEvent)
        .where(JobLifecycleEvent.id == event_id)
        .options(
            joinedload(JobLifecycleEvent.job).selectinload(Job.lifecycle_events),
            joinedload(JobLifecycleEvent.pipeline_run).selectinload(
                PipelineRun.lifecycle_events
            ),
        )
    )
    assert loaded is not None
    assert isinstance(loaded.id, UUID)
    assert loaded.job.id == job_id
    assert loaded.pipeline_run.id == run_id
    assert loaded.event_type == JobLifecycleEventType.ABSENCE_DETECTED.value
    assert (
        loaded.previous_status == loaded.new_status == JobLifecycleStatus.OBSERVED.value
    )
    assert loaded.event_metadata == {
        "consecutive_absent_runs": 1,
        "confirmation_threshold": 2,
    }
    assert loaded.occurred_at == TRANSITION_AT
    assert loaded.occurred_at.tzinfo is not None
    assert loaded.created_at.tzinfo is not None
    assert [event.id for event in loaded.job.lifecycle_events] == [event_id]
    assert [event.id for event in loaded.pipeline_run.lifecycle_events] == [event_id]


@pytest.mark.asyncio
async def test_lifecycle_metadata_default_and_optional_statuses(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session, key=f"defaults-{uuid4().hex}")
    run = await create_run(db_session, job)
    event = lifecycle_event(job, run)
    event.previous_status = None
    event.new_status = None
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)

    assert event.event_metadata == {}
    assert event.previous_status is None
    assert event.new_status is None


@pytest.mark.asyncio
async def test_lifecycle_duplicate_is_rejected_but_other_runs_and_types_are_allowed(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session, key=f"cycles-{uuid4().hex}")
    first_run = await create_run(db_session, job)
    next_run = await create_run(db_session, job)
    db_session.add_all(
        [
            lifecycle_event(job, first_run),
            lifecycle_event(job, next_run),
            lifecycle_event(
                job, next_run, event_type=JobLifecycleEventType.NOT_OBSERVED_CONFIRMED
            ),
        ]
    )
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_job_lifecycle_events_job_run_type"):
        async with db_session.begin_nested():
            db_session.add(lifecycle_event(job, first_run))
            await db_session.flush()

    events = (
        await db_session.scalars(
            select(JobLifecycleEvent).where(JobLifecycleEvent.job_id == job.id)
        )
    ).all()
    assert len(events) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_key", ["job_id", "from_version_id", "to_version_id"])
async def test_change_event_foreign_keys_reject_missing_parents(
    db_session: AsyncSession,
    foreign_key: str,
) -> None:
    job, first, second = await create_versions(db_session)
    event = change_event(job, first, second)
    setattr(event, foreign_key, uuid4())

    with pytest.raises(IntegrityError, match=f"fk_job_change_events_{foreign_key}"):
        async with db_session.begin_nested():
            db_session.add(event)
            await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_key", ["job_id", "pipeline_run_id"])
async def test_lifecycle_event_foreign_keys_reject_missing_parents(
    db_session: AsyncSession,
    foreign_key: str,
) -> None:
    job = await create_job(db_session, key=f"fk-{uuid4().hex}")
    run = await create_run(db_session, job)
    event = lifecycle_event(job, run)
    setattr(event, foreign_key, uuid4())

    with pytest.raises(IntegrityError, match=f"fk_job_lifecycle_events_{foreign_key}"):
        async with db_session.begin_nested():
            db_session.add(event)
            await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("version_number", [1, 2])
async def test_change_history_prevents_deleting_either_version(
    db_session: AsyncSession,
    version_number: int,
) -> None:
    job, first, second = await create_versions(db_session)
    db_session.add(change_event(job, first, second))
    await db_session.flush()
    version_id = first.id if version_number == 1 else second.id

    with pytest.raises(IntegrityError, match="fk_job_change_events"):
        async with db_session.begin_nested():
            await db_session.execute(
                delete(JobVersion).where(JobVersion.id == version_id)
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("parent", ["job", "pipeline_run"])
async def test_lifecycle_history_prevents_deleting_job_or_run(
    db_session: AsyncSession,
    parent: str,
) -> None:
    job = await create_job(db_session, key=f"retention-{uuid4().hex}")
    run = await create_run(db_session, job)
    db_session.add(lifecycle_event(job, run))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="fk_job_lifecycle_events"):
        async with db_session.begin_nested():
            if parent == "job":
                await db_session.execute(delete(Job).where(Job.id == job.id))
            else:
                await db_session.execute(
                    delete(PipelineRun).where(PipelineRun.id == run.id)
                )
