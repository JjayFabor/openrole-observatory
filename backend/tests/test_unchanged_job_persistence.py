from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError
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
    ChangedJobRequiresVersioningError,
    CurrentJobVersionInvariantError,
    CurrentJobVersionMissingError,
    NewJobRequiredError,
    SourceObservationRecordMismatchError,
    SourceRecordHashingError,
    UnchangedJobDatabaseError,
)
from app.jobs.hashing import compute_canonical_job_hash
from app.jobs.models import Job, JobVersion
from app.jobs.repository import JobRepository
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
    ApplyUnchangedObservationCommand,
    NewJobPersistenceService,
    PersistNewJobCommand,
    UnchangedJobPersistenceService,
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
SECOND_OBSERVED_AT = datetime(2026, 10, 6, 12, tzinfo=UTC)
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


def fixture_job() -> GreenhouseJob:
    result = parse_greenhouse_response((FIXTURE_ROOT / "jobs_v1.json").read_bytes())
    assert result.invalid_records == ()
    return result.valid_records[0]


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


async def load_version(
    session_factory: async_sessionmaker[AsyncSession],
    version_id: UUID,
) -> JobVersion:
    async with session_factory() as session:
        version = await session.get(JobVersion, version_id)
    assert version is not None
    return version


def version_state(version: JobVersion) -> tuple[Any, ...]:
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
        version.effective_to,
        version.is_current,
        version.canonical_metadata,
    )


@pytest.mark.asyncio
async def test_identical_observation_updates_only_last_seen_and_preserves_version(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_record = fixture_job()
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
    version_before = version_state(
        await load_version(database_context.session_factory, setup.version_id)
    )
    mapper = RecordingMapper()
    hasher = RecordingHasher()
    lock_requests: list[bool] = []
    original_get_job = JobRepository.get_by_source_identity

    async def record_job_lock(
        repository: JobRepository,
        source_connection_id: UUID,
        external_job_id: str,
        *,
        for_update: bool = False,
    ) -> Job | None:
        lock_requests.append(for_update)
        return await original_get_job(
            repository,
            source_connection_id,
            external_job_id,
            for_update=for_update,
        )

    monkeypatch.setattr(JobRepository, "get_by_source_identity", record_job_lock)
    result = await UnchangedJobPersistenceService(
        database_context.session_factory,
        mapper=mapper,
        hasher=hasher,
    ).apply_unchanged_observation(
        ApplyUnchangedObservationCommand(second_observation.id, source_record)
    )

    job = await load_job(database_context.session_factory, setup.job_id)
    version = await load_version(database_context.session_factory, setup.version_id)

    assert result.outcome == "unchanged"
    assert result.job_id == setup.job_id
    assert result.current_version_id == setup.version_id
    assert result.content_hash == version.content_hash
    assert result.observed_at == SECOND_OBSERVED_AT
    assert mapper.calls == [source_record]
    assert hasher.calls == [map_greenhouse_job(source_record)]
    assert lock_requests == [True]

    assert await count_rows(database_context, Job) == 1
    assert await count_rows(database_context, JobVersion) == 1
    assert await count_rows(database_context, SourceObservation) == 2
    assert job.first_seen_at == FIRST_OBSERVED_AT
    assert job.last_seen_at == SECOND_OBSERVED_AT
    assert version_state(version) == version_before
    assert version.source_observation_id == setup.first_observation.id

    async with database_context.session_factory() as session:
        second_version = await session.scalar(
            select(JobVersion).where(
                JobVersion.source_observation_id == second_observation.id
            )
        )
        second_run = await session.get(PipelineRun, second_observation.pipeline_run_id)
    assert second_version is None
    assert second_run is not None
    assert second_run.jobs_unchanged == 0


@pytest.mark.asyncio
async def test_stale_unchanged_observation_cannot_move_last_seen_backward(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_existing_job_setup(
        database_context.session_factory,
        source_record,
    )
    stale_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        source_record,
        STALE_OBSERVED_AT,
    )

    await UnchangedJobPersistenceService(
        database_context.session_factory
    ).apply_unchanged_observation(
        ApplyUnchangedObservationCommand(stale_observation.id, source_record)
    )

    job = await load_job(database_context.session_factory, setup.job_id)
    assert job.first_seen_at == FIRST_OBSERVED_AT
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert await count_rows(database_context, JobVersion) == 1


@pytest.mark.asyncio
async def test_missing_job_defers_to_new_job_path_without_creating_rows(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    source = await create_source(database_context.session_factory)
    observation = await create_observation(
        database_context.session_factory,
        source.id,
        source_record,
        SECOND_OBSERVED_AT,
    )

    with pytest.raises(NewJobRequiredError) as exc_info:
        await UnchangedJobPersistenceService(
            database_context.session_factory
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(observation.id, source_record)
        )

    assert exc_info.value.code == "NEW_JOB_REQUIRED"
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_job_without_current_version_raises_invariant_error(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    source = await create_source(database_context.session_factory)
    observation = await create_observation(
        database_context.session_factory,
        source.id,
        source_record,
        SECOND_OBSERVED_AT,
    )
    async with database_context.session_factory.begin() as session:
        job = Job(
            company_id=source.company_id,
            source_connection_id=source.id,
            external_job_id=str(source_record.id),
            first_seen_at=FIRST_OBSERVED_AT,
            last_seen_at=FIRST_OBSERVED_AT,
        )
        session.add(job)
        await session.flush()

    with pytest.raises(CurrentJobVersionMissingError) as exc_info:
        await UnchangedJobPersistenceService(
            database_context.session_factory
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(observation.id, source_record)
        )

    assert exc_info.value.code == "CURRENT_JOB_VERSION_MISSING"
    stored_job = await load_job(database_context.session_factory, job.id)
    assert stored_job.last_seen_at == FIRST_OBSERVED_AT
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_changed_hash_defers_to_versioning_without_mutating_current_state(
    database_context: DatabaseContext,
) -> None:
    original_record = fixture_job()
    setup = await create_existing_job_setup(
        database_context.session_factory,
        original_record,
    )
    changed_record = original_record.model_copy(update={"title": "Changed title"})
    changed_observation = await create_observation(
        database_context.session_factory,
        setup.source_connection.id,
        changed_record,
        SECOND_OBSERVED_AT,
    )
    version_before = version_state(
        await load_version(database_context.session_factory, setup.version_id)
    )

    with pytest.raises(ChangedJobRequiresVersioningError) as exc_info:
        await UnchangedJobPersistenceService(
            database_context.session_factory
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(changed_observation.id, changed_record)
        )

    assert exc_info.value.code == "CHANGED_JOB_REQUIRES_VERSIONING"
    job = await load_job(database_context.session_factory, setup.job_id)
    version = await load_version(database_context.session_factory, setup.version_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert version_state(version) == version_before
    assert await count_rows(database_context, JobVersion) == 1


@pytest.mark.asyncio
async def test_mismatched_record_does_not_change_freshness(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
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
    mismatched_record = source_record.model_copy(update={"id": 2002})

    with pytest.raises(SourceObservationRecordMismatchError):
        await UnchangedJobPersistenceService(
            database_context.session_factory
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(second_observation.id, mismatched_record)
        )

    job = await load_job(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert await count_rows(database_context, JobVersion) == 1


@pytest.mark.asyncio
async def test_multiple_current_versions_are_reported_as_invariant_failure(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_record = fixture_job()
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

    async def report_multiple_versions(
        _repository: JobRepository,
        _job_id: UUID,
    ) -> JobVersion | None:
        raise MultipleResultsFound("simulated corrupt current-version state")

    monkeypatch.setattr(
        JobRepository,
        "get_current_version",
        report_multiple_versions,
    )

    with pytest.raises(CurrentJobVersionInvariantError) as exc_info:
        await UnchangedJobPersistenceService(
            database_context.session_factory
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(second_observation.id, source_record)
        )

    assert exc_info.value.code == "CURRENT_JOB_VERSION_INVARIANT_FAILED"
    job = await load_job(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT


@pytest.mark.asyncio
async def test_hash_failure_is_typed_and_does_not_change_freshness(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
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

    def fail_hash(_canonical_job: CanonicalJobInput) -> str:
        raise ValueError("simulated hash failure")

    with pytest.raises(SourceRecordHashingError) as exc_info:
        await UnchangedJobPersistenceService(
            database_context.session_factory,
            hasher=fail_hash,
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(second_observation.id, source_record)
        )

    assert exc_info.value.code == "SOURCE_RECORD_HASHING_FAILED"
    assert isinstance(exc_info.value.__cause__, ValueError)
    job = await load_job(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT


@pytest.mark.asyncio
async def test_database_failure_rolls_back_last_seen_update(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_record = fixture_job()
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
    original_advance = JobRepository.advance_last_seen_at

    async def update_then_fail(
        repository: JobRepository,
        job: Job,
        observed_at: datetime,
    ) -> None:
        await original_advance(repository, job, observed_at)
        raise SQLAlchemyError("simulated failure after last_seen_at flush")

    monkeypatch.setattr(JobRepository, "advance_last_seen_at", update_then_fail)

    with pytest.raises(UnchangedJobDatabaseError) as exc_info:
        await UnchangedJobPersistenceService(
            database_context.session_factory
        ).apply_unchanged_observation(
            ApplyUnchangedObservationCommand(second_observation.id, source_record)
        )

    assert exc_info.value.code == "UNCHANGED_JOB_DATABASE_ERROR"
    assert isinstance(exc_info.value.__cause__, SQLAlchemyError)
    job = await load_job(database_context.session_factory, setup.job_id)
    assert job.last_seen_at == FIRST_OBSERVED_AT
    assert await count_rows(database_context, JobVersion) == 1
