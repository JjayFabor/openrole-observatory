from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.companies.models import Company
from app.config import get_settings
from app.database.engine import create_database_engine
from app.jobs.errors import (
    ChangedJobDatabaseError,
    CurrentJobVersionMissingError,
    HistoricalJobContentAlreadyExistsError,
    NewJobRequiredError,
    SourceObservationRecordMismatchError,
    StaleJobObservationError,
    UnchangedJobRequiresFreshnessUpdateError,
)
from app.jobs.hashing import compute_canonical_job_hash
from app.jobs.models import Job, JobVersion
from app.jobs.repository import JobRepository
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
    ApplyChangedObservationCommand,
    ChangedJobPersistenceService,
    NewJobPersistenceService,
    PersistNewJobCommand,
)
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.sources.greenhouse.validation import parse_greenhouse_response
from app.sources.models import SourceConnection, SourceProvider
from tests.database_counts import (
    TableCounts,
    capture_table_counts,
    count_rows_since_baseline,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "greenhouse"
FIRST_OBSERVED_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)
SECOND_OBSERVED_AT = datetime(2026, 10, 8, 12, tzinfo=UTC)
THIRD_OBSERVED_AT = datetime(2026, 10, 9, 12, tzinfo=UTC)
STALE_OBSERVED_AT = datetime(2026, 10, 4, 12, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]
    baseline_counts: TableCounts


@dataclass(frozen=True, slots=True)
class ExistingJobSetup:
    source_connection: SourceConnection
    first_observation: SourceObservation
    job_id: UUID
    version_id: UUID


class RecordingMapper:
    def __init__(self) -> None:
        self.calls: list[GreenhouseJob] = []

    def __call__(self, source_record: GreenhouseJob) -> CanonicalJobInput:
        self.calls.append(source_record)
        return map_greenhouse_job(source_record)


class RecordingHasher:
    def __init__(self) -> None:
        self.calls: list[CanonicalJobInput] = []

    def __call__(self, canonical_job: CanonicalJobInput) -> str:
        self.calls.append(canonical_job)
        return compute_canonical_job_hash(canonical_job)


@pytest_asyncio.fixture
async def database_context() -> AsyncIterator[DatabaseContext]:
    engine = create_database_engine(get_settings().database_url)

    async with engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        baseline_counts = await capture_table_counts(connection)

        try:
            yield DatabaseContext(
                engine,
                connection,
                session_factory,
                baseline_counts,
            )
        finally:
            if transaction.is_active:
                await transaction.rollback()

    await engine.dispose()


def fixture_job(name: str) -> GreenhouseJob:
    result = parse_greenhouse_response((FIXTURE_ROOT / name).read_bytes())
    assert result.invalid_records == ()
    return next(job for job in result.valid_records if job.id == 1001)


async def create_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> SourceConnection:
    suffix = uuid4().hex
    async with session_factory.begin() as session:
        source = SourceConnection(
            company=Company(name=f"Company {suffix}", slug=f"company-{suffix}"),
            provider=SourceProvider.GREENHOUSE.value,
            external_account_key=f"board-{suffix}",
        )
        session.add(source)
        await session.flush()
    return source


async def create_observation(
    session_factory: async_sessionmaker[AsyncSession],
    source_connection_id: UUID,
    source_record: GreenhouseJob,
    observed_at: datetime,
) -> SourceObservation:
    suffix = uuid4().hex
    async with session_factory.begin() as session:
        pipeline_run = PipelineRun(
            source_connection_id=source_connection_id,
            status=PipelineRunStatus.RUNNING.value,
            started_at=observed_at,
        )
        raw_snapshot = RawSnapshot(
            pipeline_run=pipeline_run,
            r2_object_key=f"bronze/tests/run={suffix}/jobs.json",
            content_hash="a" * 64,
            content_type="application/json",
            content_length_bytes=100,
            record_count=1,
            retrieved_at=observed_at,
        )
        observation = SourceObservation(
            pipeline_run=pipeline_run,
            source_connection_id=source_connection_id,
            raw_snapshot=raw_snapshot,
            external_job_id=str(source_record.id),
            raw_record_locator="jobs[0]",
            source_content_hash="b" * 64,
            observed_at=observed_at,
            source_metadata={"source_record_index": 0},
        )
        session.add(observation)
        await session.flush()
    return observation


async def create_existing_job_setup(
    session_factory: async_sessionmaker[AsyncSession],
    source_record: GreenhouseJob,
) -> ExistingJobSetup:
    source = await create_source(session_factory)
    first_observation = await create_observation(
        session_factory,
        source.id,
        source_record,
        FIRST_OBSERVED_AT,
    )
    result = await NewJobPersistenceService(session_factory).create_new_job(
        PersistNewJobCommand(first_observation.id, source_record)
    )
    return ExistingJobSetup(
        source_connection=source,
        first_observation=first_observation,
        job_id=result.job_id,
        version_id=result.job_version_id,
    )


async def count_rows(
    database_context: DatabaseContext,
    model: type[Job] | type[JobVersion] | type[SourceObservation],
) -> int:
    return await count_rows_since_baseline(
        database_context.session_factory,
        model,
        database_context.baseline_counts,
    )


async def load_job(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
) -> Job:
    async with session_factory() as session:
        job = await session.get(Job, job_id)
    assert job is not None
    return job


async def load_versions(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
) -> list[JobVersion]:
    async with session_factory() as session:
        versions = list(
            (
                await session.scalars(
                    select(JobVersion)
                    .where(JobVersion.job_id == job_id)
                    .order_by(JobVersion.version_number)
                )
            ).all()
        )
    return versions


def immutable_version_state(version: JobVersion) -> tuple[Any, ...]:
    return (
        version.id,
        version.job_id,
        version.source_observation_id,
        version.version_number,
        version.content_hash,
        version.title,
        version.description,
        version.location_text,
        version.city,
        version.region,
        version.country_code,
        version.workplace_type,
        version.employment_type,
        version.salary_min,
        version.salary_max,
        version.salary_currency,
        version.salary_period,
        version.source_url,
        version.source_published_at,
        version.source_updated_at,
        version.effective_from,
        version.canonical_metadata,
    )


@pytest.mark.asyncio
async def test_changed_observation_closes_v1_and_creates_v2_atomically(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_record = fixture_job("jobs_v1.json")
    changed_record = fixture_job("jobs_v2.json")
    setup = await create_existing_job_setup(
        database_context.session_factory,
        original_record,
    )
    second_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )
    original_job = await load_job(database_context.session_factory, setup.job_id)
    original_identity = (
        original_job.id,
        original_job.company_id,
        original_job.source_connection_id,
        original_job.external_job_id,
    )
    original_version = (
        await load_versions(
            database_context.session_factory,
            setup.job_id,
        )
    )[0]
    v1_immutable_state = immutable_version_state(original_version)
    mapper = RecordingMapper()
    hasher = RecordingHasher()
    job_lock_requests: list[bool] = []
    version_lock_requests: list[bool] = []
    original_get_job = JobRepository.get_by_source_identity
    original_get_current = JobRepository.get_current_version

    async def record_job_lock(
        repository: JobRepository,
        source_connection_id: UUID,
        external_job_id: str,
        *,
        for_update: bool = False,
    ) -> Job | None:
        job_lock_requests.append(for_update)
        return await original_get_job(
            repository,
            source_connection_id,
            external_job_id,
            for_update=for_update,
        )

    async def record_version_lock(
        repository: JobRepository,
        job_id: UUID,
        *,
        for_update: bool = False,
    ) -> JobVersion | None:
        version_lock_requests.append(for_update)
        return await original_get_current(
            repository,
            job_id,
            for_update=for_update,
        )

    monkeypatch.setattr(JobRepository, "get_by_source_identity", record_job_lock)
    monkeypatch.setattr(JobRepository, "get_current_version", record_version_lock)

    result = await ChangedJobPersistenceService(
        database_context.session_factory,
        mapper=mapper,
        hasher=hasher,
    ).apply_changed_observation(
        ApplyChangedObservationCommand(second_observation.id, changed_record)
    )

    job = await load_job(database_context.session_factory, setup.job_id)
    versions = await load_versions(database_context.session_factory, setup.job_id)
    v1, v2 = versions
    canonical_v2 = map_greenhouse_job(changed_record)
    expected_v2_hash = compute_canonical_job_hash(canonical_v2)

    assert result.outcome == "changed"
    assert result.job_id == setup.job_id
    assert result.previous_version_id == setup.version_id
    assert result.new_version_id == v2.id
    assert result.previous_version_number == 1
    assert result.new_version_number == 2
    assert result.previous_content_hash == v1.content_hash
    assert result.new_content_hash == expected_v2_hash
    assert result.observed_at == SECOND_OBSERVED_AT
    assert mapper.calls == [changed_record]
    assert hasher.calls == [canonical_v2]
    assert job_lock_requests == [True]
    assert version_lock_requests == [True]

    assert await count_rows(database_context, Job) == 1
    assert await count_rows(database_context, JobVersion) == 2
    assert await count_rows(database_context, SourceObservation) == 2
    assert (
        job.id,
        job.company_id,
        job.source_connection_id,
        job.external_job_id,
    ) == original_identity
    assert job.first_seen_at == FIRST_OBSERVED_AT
    assert job.last_seen_at == SECOND_OBSERVED_AT

    assert immutable_version_state(v1) == v1_immutable_state
    assert v1.source_observation_id == setup.first_observation.id
    assert v1.version_number == 1
    assert v1.is_current is False
    assert v1.effective_from == FIRST_OBSERVED_AT
    assert v1.effective_to == SECOND_OBSERVED_AT

    assert v2.source_observation_id == second_observation.id
    assert v2.version_number == 2
    assert v2.content_hash == expected_v2_hash
    assert v2.title == canonical_v2.title
    assert v2.description == canonical_v2.description
    assert v2.location_text == canonical_v2.location_text
    assert v2.city == canonical_v2.city
    assert v2.region == canonical_v2.region
    assert v2.country_code == canonical_v2.country_code
    assert v2.workplace_type == canonical_v2.workplace_type
    assert v2.employment_type == canonical_v2.employment_type
    assert v2.salary_min == canonical_v2.salary_min
    assert v2.salary_max == canonical_v2.salary_max
    assert v2.salary_currency == canonical_v2.salary_currency
    assert v2.salary_period == canonical_v2.salary_period
    assert v2.source_url == str(canonical_v2.source_url)
    assert v2.source_published_at == canonical_v2.source_published_at
    assert v2.source_updated_at == canonical_v2.source_updated_at
    assert v2.canonical_metadata == canonical_v2.canonical_metadata
    assert v2.effective_from == SECOND_OBSERVED_AT
    assert v2.effective_to is None
    assert v2.is_current is True

    async with database_context.session_factory() as session:
        second_run = await session.get(PipelineRun, second_observation.pipeline_run_id)
    assert second_run is not None
    assert second_run.jobs_changed == 0


@pytest.mark.asyncio
async def test_same_hash_defers_to_unchanged_path_without_transition(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job("jobs_v1.json")
    setup = await create_existing_job_setup(
        database_context.session_factory,
        source_record,
    )
    second_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        source_record,
        SECOND_OBSERVED_AT,
    )

    with pytest.raises(UnchangedJobRequiresFreshnessUpdateError) as exc_info:
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(second_observation.id, source_record)
        )

    assert exc_info.value.code == "UNCHANGED_JOB_REQUIRES_FRESHNESS_UPDATE"
    job = await load_job(database_context.session_factory, setup.job_id)
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert len(versions) == 1
    assert versions[0].is_current is True
    assert versions[0].effective_to is None


@pytest.mark.asyncio
async def test_missing_job_defers_to_new_job_path(
    database_context: DatabaseContext,
) -> None:
    changed_record = fixture_job("jobs_v2.json")
    source = await create_source(database_context.session_factory)
    observation = await create_observation(
        database_context.session_factory,
        source.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )

    with pytest.raises(NewJobRequiredError) as exc_info:
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(observation.id, changed_record)
        )

    assert exc_info.value.code == "NEW_JOB_REQUIRED"
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_missing_current_version_does_not_change_job(
    database_context: DatabaseContext,
) -> None:
    changed_record = fixture_job("jobs_v2.json")
    source = await create_source(database_context.session_factory)
    observation = await create_observation(
        database_context.session_factory,
        source.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )
    async with database_context.session_factory.begin() as session:
        job = Job(
            company_id=source.company_id,
            source_connection_id=source.id,
            external_job_id=str(changed_record.id),
            first_seen_at=FIRST_OBSERVED_AT,
            last_seen_at=FIRST_OBSERVED_AT,
        )
        session.add(job)
        await session.flush()

    with pytest.raises(CurrentJobVersionMissingError):
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(observation.id, changed_record)
        )

    stored_job = await load_job(database_context.session_factory, job.id)
    assert stored_job.last_seen_at == FIRST_OBSERVED_AT
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_stale_changed_observation_cannot_rewrite_history_backward(
    database_context: DatabaseContext,
) -> None:
    original_record = fixture_job("jobs_v1.json")
    changed_record = fixture_job("jobs_v2.json")
    setup = await create_existing_job_setup(
        database_context.session_factory,
        original_record,
    )
    stale_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        changed_record,
        STALE_OBSERVED_AT,
    )

    with pytest.raises(StaleJobObservationError) as exc_info:
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(stale_observation.id, changed_record)
        )

    assert exc_info.value.code == "STALE_JOB_OBSERVATION"
    job = await load_job(database_context.session_factory, setup.job_id)
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert len(versions) == 1
    assert versions[0].is_current is True
    assert versions[0].effective_to is None


@pytest.mark.asyncio
async def test_repeated_historical_hash_has_stable_outcome(
    database_context: DatabaseContext,
) -> None:
    original_record = fixture_job("jobs_v1.json")
    changed_record = fixture_job("jobs_v2.json")
    setup = await create_existing_job_setup(
        database_context.session_factory,
        original_record,
    )
    second_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )
    transition = await ChangedJobPersistenceService(
        database_context.session_factory
    ).apply_changed_observation(
        ApplyChangedObservationCommand(second_observation.id, changed_record)
    )
    third_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        original_record,
        THIRD_OBSERVED_AT,
    )

    with pytest.raises(HistoricalJobContentAlreadyExistsError) as exc_info:
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(third_observation.id, original_record)
        )

    assert exc_info.value.code == "HISTORICAL_JOB_CONTENT_ALREADY_EXISTS"
    assert exc_info.value.historical_version_id == setup.version_id
    job = await load_job(database_context.session_factory, setup.job_id)
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == SECOND_OBSERVED_AT
    assert len(versions) == 2
    assert versions[0].is_current is False
    assert versions[1].id == transition.new_version_id
    assert versions[1].is_current is True
    assert versions[1].effective_to is None


@pytest.mark.asyncio
async def test_new_version_failure_rolls_back_closure_and_freshness(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_record = fixture_job("jobs_v1.json")
    changed_record = fixture_job("jobs_v2.json")
    setup = await create_existing_job_setup(
        database_context.session_factory,
        original_record,
    )
    second_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )

    async def fail_new_version(
        _repository: JobRepository,
        _version: JobVersion,
    ) -> JobVersion:
        raise SQLAlchemyError("simulated failure inserting Version 2")

    monkeypatch.setattr(JobRepository, "add_version", fail_new_version)

    with pytest.raises(ChangedJobDatabaseError) as exc_info:
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(second_observation.id, changed_record)
        )

    assert exc_info.value.code == "CHANGED_JOB_DATABASE_ERROR"
    assert isinstance(exc_info.value.__cause__, SQLAlchemyError)
    job = await load_job(database_context.session_factory, setup.job_id)
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert len(versions) == 1
    assert versions[0].is_current is True
    assert versions[0].effective_to is None


@pytest.mark.asyncio
async def test_database_still_rejects_two_current_versions(
    database_context: DatabaseContext,
) -> None:
    original_record = fixture_job("jobs_v1.json")
    changed_record = fixture_job("jobs_v2.json")
    setup = await create_existing_job_setup(
        database_context.session_factory,
        original_record,
    )
    second_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )
    canonical_v2 = map_greenhouse_job(changed_record)

    async with database_context.session_factory.begin() as session:
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    JobVersion(
                        job_id=setup.job_id,
                        source_observation_id=second_observation.id,
                        version_number=2,
                        content_hash=compute_canonical_job_hash(canonical_v2),
                        title=canonical_v2.title,
                        description=canonical_v2.description,
                        location_text=canonical_v2.location_text,
                        source_url=str(canonical_v2.source_url),
                        effective_from=SECOND_OBSERVED_AT,
                        is_current=True,
                    )
                )
                await session.flush()

    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert len(versions) == 1
    assert versions[0].is_current is True


@pytest.mark.asyncio
async def test_mismatched_source_record_does_not_change_history(
    database_context: DatabaseContext,
) -> None:
    original_record = fixture_job("jobs_v1.json")
    changed_record = fixture_job("jobs_v2.json")
    setup = await create_existing_job_setup(
        database_context.session_factory,
        original_record,
    )
    second_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )
    mismatched_record = changed_record.model_copy(update={"id": 2002})

    with pytest.raises(SourceObservationRecordMismatchError):
        await ChangedJobPersistenceService(
            database_context.session_factory
        ).apply_changed_observation(
            ApplyChangedObservationCommand(second_observation.id, mismatched_record)
        )

    job = await load_job(database_context.session_factory, setup.job_id)
    versions = await load_versions(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert len(versions) == 1
    assert versions[0].is_current is True
