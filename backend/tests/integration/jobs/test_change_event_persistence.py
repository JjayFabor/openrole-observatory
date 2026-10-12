from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import app.jobs.service as service_module
from app.jobs.change_detection import JobVersionComparable, diff_job_versions
from app.jobs.changes import FieldChange
from app.jobs.errors import (
    ChangedJobDatabaseError,
    JobDiffInvariantError,
    SourceObservationAlreadyMaterializedError,
)
from app.jobs.models import JobChangeEvent, JobLifecycleEvent, JobVersion
from app.jobs.repository import JobRepository
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
    ApplyChangedObservationCommand,
    ApplyUnchangedObservationCommand,
    ChangedJobPersistenceService,
    ChangedJobResult,
    NewJobPersistenceService,
    PersistNewJobCommand,
    UnchangedJobPersistenceService,
)
from tests.test_changed_job_persistence import (
    FIRST_OBSERVED_AT,
    SECOND_OBSERVED_AT,
    DatabaseContext,
    create_observation,
    create_source,
    fixture_job,
    immutable_version_state,
    load_job,
    load_versions,
)
from tests.test_changed_job_persistence import database_context as database_context


@dataclass(frozen=True, slots=True)
class PreparedTransition:
    job_id: UUID
    previous_version_id: UUID
    command: ApplyChangedObservationCommand


def canonical_job(**overrides: object) -> CanonicalJobInput:
    return CanonicalJobInput.model_validate(
        {
            "external_job_id": "1001",
            "title": "Backend Engineer",
            "source_url": "https://example.com/jobs/1001",
            "location_text": "Remote",
            "workplace_type": "remote",
            **overrides,
        }
    )


async def prepare_transition(
    context: DatabaseContext,
    previous: CanonicalJobInput,
) -> PreparedTransition:
    source_record = fixture_job("jobs_v1.json")
    source = await create_source(context.session_factory)
    first_observation = await create_observation(
        context.session_factory, source.id, source_record, FIRST_OBSERVED_AT
    )
    first = await NewJobPersistenceService(
        context.session_factory, mapper=lambda _: previous
    ).create_new_job(PersistNewJobCommand(first_observation.id, source_record))
    next_observation = await create_observation(
        context.session_factory, source.id, source_record, SECOND_OBSERVED_AT
    )
    return PreparedTransition(
        job_id=first.job_id,
        previous_version_id=first.job_version_id,
        command=ApplyChangedObservationCommand(next_observation.id, source_record),
    )


async def apply_transition(
    context: DatabaseContext,
    setup: PreparedTransition,
    current: CanonicalJobInput,
) -> ChangedJobResult:
    return await ChangedJobPersistenceService(
        context.session_factory, mapper=lambda _: current
    ).apply_changed_observation(setup.command)


async def load_events(context: DatabaseContext, job_id: UUID) -> list[JobChangeEvent]:
    async with context.session_factory() as session:
        return list(
            await session.scalars(
                select(JobChangeEvent)
                .where(JobChangeEvent.job_id == job_id)
                .order_by(JobChangeEvent.field_name)
            )
        )


async def assert_transition_rolled_back(
    context: DatabaseContext,
    setup: PreparedTransition,
    previous: JobVersion,
) -> None:
    versions = await load_versions(context.session_factory, setup.job_id)
    assert len(versions) == 1
    assert immutable_version_state(versions[0]) == immutable_version_state(previous)
    assert versions[0].is_current is True
    assert versions[0].effective_to is None
    assert await load_events(context, setup.job_id) == []
    job = await load_job(context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT


@pytest.mark.asyncio
async def test_single_field_transition_calls_diff_once_and_preserves_provenance(
    database_context: DatabaseContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = canonical_job()
    current = canonical_job(workplace_type="hybrid")
    setup = await prepare_transition(database_context, previous)
    original_version = (
        await load_versions(database_context.session_factory, setup.job_id)
    )[0]
    calls: list[tuple[JobVersionComparable, JobVersionComparable]] = []

    def record_diff(
        old: JobVersionComparable, new: JobVersionComparable
    ) -> list[FieldChange]:
        assert isinstance(old, JobVersionComparable)
        assert isinstance(new, JobVersionComparable)
        calls.append((old, new))
        return diff_job_versions(old, new)

    monkeypatch.setattr(service_module, "diff_job_versions", record_diff)
    result = await apply_transition(database_context, setup, current)

    assert len(calls) == 1
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert [version.version_number for version in versions] == [1, 2]
    assert immutable_version_state(versions[0]) == immutable_version_state(
        original_version
    )
    assert versions[0].is_current is False
    assert versions[0].effective_to == SECOND_OBSERVED_AT
    assert versions[1].is_current is True
    assert versions[1].source_observation_id == setup.command.source_observation_id
    events = await load_events(database_context, setup.job_id)
    assert len(events) == 1
    event = events[0]
    assert event.field_name == "workplace_type"
    assert event.change_type == "modified"
    assert (event.old_value, event.new_value) == ("remote", "hybrid")
    assert event.job_id == result.job_id == setup.job_id
    assert event.from_version_id == result.previous_version_id == versions[0].id
    assert event.to_version_id == result.new_version_id == versions[1].id
    assert event.detected_at == versions[1].effective_from == SECOND_OBSERVED_AT
    assert event.created_at is not None
    job = await load_job(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == SECOND_OBSERVED_AT
    assert job.consecutive_absent_runs == 0
    assert job.absence_first_detected_at is None
    async with database_context.session_factory() as session:
        assert (
            await session.scalar(
                select(JobLifecycleEvent).where(
                    JobLifecycleEvent.job_id == setup.job_id
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_multiple_fields_persist_one_event_per_diff(
    database_context: DatabaseContext,
) -> None:
    previous = canonical_job()
    current = canonical_job(
        location_text="Berlin, Germany",
        workplace_type="hybrid",
        salary_min=Decimal("65000.00"),
        salary_max=Decimal("80000.00"),
    )
    setup = await prepare_transition(database_context, previous)

    await apply_transition(database_context, setup, current)

    events = await load_events(database_context, setup.job_id)
    assert [event.field_name for event in events] == [
        "location_text",
        "salary_max",
        "salary_min",
        "workplace_type",
    ]
    expected = diff_job_versions(
        JobVersionComparable.from_canonical_job(previous),
        JobVersionComparable.from_canonical_job(current),
    )
    assert {
        event.field_name: (event.change_type, event.old_value, event.new_value)
        for event in events
    } == {
        change.field_name: (
            change.change_type.value,
            change.old_value,
            change.new_value,
        )
        for change in expected
    }
    assert (
        next(event for event in events if event.field_name == "salary_min").new_value
        == "65000"
    )
    assert all(event.detected_at == SECOND_OBSERVED_AT for event in events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "field_name",
        "previous_value",
        "current_value",
        "change_type",
        "old_json",
        "new_json",
    ),
    [
        ("salary_min", None, Decimal("65000.00"), "added", None, "65000"),
        ("salary_currency", "EUR", None, "removed", "EUR", None),
    ],
)
async def test_added_and_removed_values_round_trip_as_json(
    database_context: DatabaseContext,
    field_name: str,
    previous_value: object,
    current_value: object,
    change_type: str,
    old_json: object,
    new_json: object,
) -> None:
    setup = await prepare_transition(
        database_context, canonical_job(**{field_name: previous_value})
    )

    await apply_transition(
        database_context, setup, canonical_job(**{field_name: current_value})
    )

    events = await load_events(database_context, setup.job_id)
    assert len(events) == 1
    assert events[0].field_name == field_name
    assert events[0].change_type == change_type
    assert (events[0].old_value, events[0].new_value) == (old_json, new_json)


@pytest.mark.asyncio
async def test_full_large_descriptions_and_nested_metadata_round_trip(
    database_context: DatabaseContext,
) -> None:
    old_text = "<p>Build APIs — 工程.</p>" * 5000
    new_text = "<p>Build distributed systems — 設計.</p>" * 6000
    previous = canonical_job(
        description=old_text,
        canonical_metadata={
            "departments": ["Platform"],
            "nested": {"flags": [True, None]},
        },
    )
    current = canonical_job(
        description=new_text,
        canonical_metadata={
            "departments": ["Research"],
            "nested": {"flags": [False, 1.5]},
        },
    )
    setup = await prepare_transition(database_context, previous)

    await apply_transition(database_context, setup, current)

    events = {
        event.field_name: event
        for event in await load_events(database_context, setup.job_id)
    }
    assert set(events) == {"description", "canonical_metadata"}
    assert events["description"].old_value == old_text
    assert events["description"].new_value == new_text
    assert events["canonical_metadata"].old_value == previous.canonical_metadata
    assert events["canonical_metadata"].new_value == current.canonical_metadata


@pytest.mark.asyncio
async def test_initial_and_unchanged_versions_create_no_events(
    database_context: DatabaseContext,
) -> None:
    previous = canonical_job()
    setup = await prepare_transition(database_context, previous)
    assert await load_events(database_context, setup.job_id) == []
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert len(versions) == 1

    await UnchangedJobPersistenceService(
        database_context.session_factory, mapper=lambda _: previous
    ).apply_unchanged_observation(
        ApplyUnchangedObservationCommand(
            setup.command.source_observation_id, setup.command.source_record
        )
    )

    assert await load_events(database_context, setup.job_id) == []
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert len(versions) == 1
    assert versions[0].is_current is True
    job = await load_job(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == SECOND_OBSERVED_AT


@pytest.mark.asyncio
async def test_replaying_transition_does_not_duplicate_versions_or_events(
    database_context: DatabaseContext,
) -> None:
    current = canonical_job(workplace_type="hybrid")
    setup = await prepare_transition(database_context, canonical_job())
    result = await apply_transition(database_context, setup, current)
    original_events = await load_events(database_context, setup.job_id)

    with pytest.raises(SourceObservationAlreadyMaterializedError):
        await apply_transition(database_context, setup, current)

    assert len(await load_versions(database_context.session_factory, setup.job_id)) == 2
    assert [
        event.id for event in await load_events(database_context, setup.job_id)
    ] == [event.id for event in original_events]
    assert original_events[0].to_version_id == result.new_version_id


@pytest.mark.asyncio
async def test_database_rejects_duplicate_transition_field(
    database_context: DatabaseContext,
) -> None:
    setup = await prepare_transition(database_context, canonical_job())
    await apply_transition(
        database_context, setup, canonical_job(workplace_type="hybrid")
    )
    event = (await load_events(database_context, setup.job_id))[0]

    with pytest.raises(IntegrityError, match="uq_job_change_events_from_to_field"):
        async with database_context.session_factory.begin() as session:
            session.add(
                JobChangeEvent(
                    job_id=event.job_id,
                    from_version_id=event.from_version_id,
                    to_version_id=event.to_version_id,
                    field_name=event.field_name,
                    change_type=event.change_type,
                    old_value=event.old_value,
                    new_value=event.new_value,
                    detected_at=event.detected_at,
                )
            )
            await session.flush()

    assert len(await load_events(database_context, setup.job_id)) == 1
    assert len(await load_versions(database_context.session_factory, setup.job_id)) == 2


@pytest.mark.asyncio
async def test_partial_event_insert_failure_rolls_back_entire_transition_and_can_retry(
    database_context: DatabaseContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = await prepare_transition(database_context, canonical_job())
    previous = (await load_versions(database_context.session_factory, setup.job_id))[0]
    current = canonical_job(location_text="Berlin", workplace_type="hybrid")
    original_add = JobRepository.add_change_events
    failed_version_ids: list[UUID] = []

    async def insert_one_then_duplicate(
        repository: JobRepository, events: Sequence[JobChangeEvent]
    ) -> None:
        assert len(events) == 2
        next_version = await repository.get_current_version(setup.job_id)
        assert next_version is not None
        assert next_version.id == events[0].to_version_id
        assert next_version.version_number == 2
        old_version = await repository.get_version_by_source_observation(
            previous.source_observation_id
        )
        assert old_version is not None
        assert old_version.is_current is False
        assert old_version.effective_to == SECOND_OBSERVED_AT
        failed_version_ids.append(next_version.id)
        await original_add(repository, events[:1])
        assert events[0].id is not None
        assert events[0].created_at is not None
        events[1].field_name = events[0].field_name
        await original_add(repository, events[1:])

    monkeypatch.setattr(JobRepository, "add_change_events", insert_one_then_duplicate)
    with pytest.raises(ChangedJobDatabaseError) as caught:
        await apply_transition(database_context, setup, current)

    assert isinstance(caught.value.__cause__, IntegrityError)
    assert "uq_job_change_events_from_to_field" in str(caught.value.__cause__)
    assert len(failed_version_ids) == 1
    await assert_transition_rolled_back(database_context, setup, previous)
    async with database_context.session_factory() as session:
        assert await session.get(JobVersion, failed_version_ids[0]) is None

    monkeypatch.setattr(JobRepository, "add_change_events", original_add)
    result = await apply_transition(database_context, setup, current)
    assert result.new_version_id != failed_version_ids[0]
    assert len(await load_versions(database_context.session_factory, setup.job_id)) == 2
    assert len(await load_events(database_context, setup.job_id)) == 2


@pytest.mark.asyncio
async def test_diff_generation_failure_rolls_back_transition(
    database_context: DatabaseContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = await prepare_transition(database_context, canonical_job())
    previous = (await load_versions(database_context.session_factory, setup.job_id))[0]

    def fail_diff(
        old: JobVersionComparable, new: JobVersionComparable
    ) -> list[FieldChange]:
        raise ValueError("simulated diff generation failure")

    monkeypatch.setattr(service_module, "diff_job_versions", fail_diff)
    with pytest.raises(ValueError, match="simulated diff generation failure"):
        await apply_transition(
            database_context, setup, canonical_job(workplace_type="hybrid")
        )

    await assert_transition_rolled_back(database_context, setup, previous)


@pytest.mark.asyncio
async def test_different_hashes_with_identical_fields_raise_invariant_and_roll_back(
    database_context: DatabaseContext,
) -> None:
    canonical = canonical_job()
    setup = await prepare_transition(database_context, canonical)
    previous = (await load_versions(database_context.session_factory, setup.job_id))[0]
    assert previous.content_hash != "f" * 64

    with pytest.raises(JobDiffInvariantError) as caught:
        await ChangedJobPersistenceService(
            database_context.session_factory,
            mapper=lambda _: canonical,
            hasher=lambda _: "f" * 64,
        ).apply_changed_observation(setup.command)

    assert caught.value.code == "JOB_DIFF_INVARIANT_FAILED"
    await assert_transition_rolled_back(database_context, setup, previous)
