from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import joinedload

from app.companies.models import Company
from app.config import get_settings
from app.database.engine import create_database_engine
from app.jobs.errors import (
    ExistingJobRequiresComparisonError,
    NewJobDatabaseError,
    NewJobUnsupportedProviderError,
    SourceObservationAlreadyMaterializedError,
    SourceObservationNotFoundError,
    SourceObservationRecordMismatchError,
    SourceRecordNormalizationError,
)
from app.jobs.hashing import compute_canonical_job_hash
from app.jobs.models import Job, JobLifecycleStatus, JobVersion
from app.jobs.repository import JobRepository
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
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
OBSERVED_AT = datetime(2026, 10, 6, 12, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]
    baseline_counts: TableCounts


@dataclass(frozen=True, slots=True)
class ObservationSetup:
    company: Company
    source_connection: SourceConnection
    pipeline_run: PipelineRun
    raw_snapshot: RawSnapshot
    observation: SourceObservation


class RecordingMapper:
    def __init__(self, canonical_job: CanonicalJobInput) -> None:
        self.canonical_job = canonical_job
        self.calls: list[GreenhouseJob] = []

    def __call__(self, source_record: GreenhouseJob) -> CanonicalJobInput:
        self.calls.append(source_record)
        return self.canonical_job


class RecordingHasher:
    def __init__(self, content_hash: str) -> None:
        self.content_hash = content_hash
        self.calls: list[CanonicalJobInput] = []

    def __call__(self, canonical_job: CanonicalJobInput) -> str:
        self.calls.append(canonical_job)
        return self.content_hash


class ConstraintViolation(Exception):
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name
        super().__init__(constraint_name)


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


async def create_observation_setup(
    session_factory: async_sessionmaker[AsyncSession],
    source_record: GreenhouseJob,
    *,
    provider: str = SourceProvider.GREENHOUSE.value,
) -> ObservationSetup:
    suffix = uuid4().hex
    async with session_factory.begin() as session:
        company = Company(name=f"Company {suffix}", slug=f"company-{suffix}")
        source_connection = SourceConnection(
            company=company,
            provider=provider,
            external_account_key=f"board-{suffix}",
        )
        pipeline_run = PipelineRun(
            source_connection=source_connection,
            status=PipelineRunStatus.RUNNING.value,
            started_at=OBSERVED_AT,
        )
        raw_snapshot = RawSnapshot(
            pipeline_run=pipeline_run,
            r2_object_key=f"bronze/tests/run={suffix}/jobs.json",
            content_hash="a" * 64,
            content_type="application/json",
            content_length_bytes=100,
            record_count=1,
            retrieved_at=OBSERVED_AT,
        )
        observation = SourceObservation(
            pipeline_run=pipeline_run,
            source_connection=source_connection,
            raw_snapshot=raw_snapshot,
            external_job_id=str(source_record.id),
            raw_record_locator="jobs[0]",
            source_content_hash="b" * 64,
            observed_at=OBSERVED_AT,
            source_metadata={"source_record_index": 0},
        )
        session.add(observation)
        await session.flush()

    return ObservationSetup(
        company=company,
        source_connection=source_connection,
        pipeline_run=pipeline_run,
        raw_snapshot=raw_snapshot,
        observation=observation,
    )


async def count_rows(
    database_context: DatabaseContext,
    model: type[Job] | type[JobVersion],
) -> int:
    return await count_rows_since_baseline(
        database_context.session_factory,
        model,
        database_context.baseline_counts,
    )


async def load_job_and_version(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    job_version_id: UUID,
) -> tuple[Job, JobVersion]:
    async with session_factory() as session:
        job = (await session.scalars(select(Job).where(Job.id == job_id))).one()
        version = (
            await session.scalars(
                select(JobVersion)
                .options(
                    joinedload(JobVersion.source_observation).joinedload(
                        SourceObservation.raw_snapshot
                    )
                )
                .where(JobVersion.id == job_version_id)
            )
        ).one()
    return job, version


@pytest.mark.asyncio
async def test_new_job_creates_identity_version_and_complete_lineage(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )
    canonical_job = map_greenhouse_job(source_record)
    expected_hash = compute_canonical_job_hash(canonical_job)

    result = await NewJobPersistenceService(
        database_context.session_factory
    ).create_new_job(
        PersistNewJobCommand(
            source_observation_id=setup.observation.id,
            source_record=source_record,
        )
    )
    job, version = await load_job_and_version(
        database_context.session_factory,
        result.job_id,
        result.job_version_id,
    )

    assert await count_rows(database_context, Job) == 1
    assert await count_rows(database_context, JobVersion) == 1
    assert result.version_number == 1
    assert result.content_hash == expected_hash

    assert job.company_id == setup.company.id
    assert job.source_connection_id == setup.source_connection.id
    assert job.external_job_id == setup.observation.external_job_id
    assert job.first_seen_at == setup.observation.observed_at
    assert job.last_seen_at == setup.observation.observed_at
    assert job.lifecycle_status == JobLifecycleStatus.OBSERVED.value
    assert job.no_longer_observed_at is None
    assert job.reappeared_at is None

    assert version.job_id == job.id
    assert version.source_observation_id == setup.observation.id
    assert version.version_number == 1
    assert version.content_hash == expected_hash
    assert version.title == canonical_job.title
    assert version.description == canonical_job.description
    assert version.location_text == canonical_job.location_text
    assert version.city == canonical_job.city
    assert version.region == canonical_job.region
    assert version.country_code == canonical_job.country_code
    assert version.workplace_type == canonical_job.workplace_type
    assert version.employment_type == canonical_job.employment_type
    assert version.salary_min == canonical_job.salary_min
    assert version.salary_max == canonical_job.salary_max
    assert version.salary_currency == canonical_job.salary_currency
    assert version.salary_period == canonical_job.salary_period
    assert version.source_url == str(canonical_job.source_url)
    assert version.source_published_at == canonical_job.source_published_at
    assert version.source_updated_at == canonical_job.source_updated_at
    assert version.canonical_metadata == canonical_job.canonical_metadata
    assert version.effective_from == setup.observation.observed_at
    assert version.effective_to is None
    assert version.is_current is True
    assert version.source_observation.raw_snapshot.id == setup.raw_snapshot.id

    async with database_context.session_factory() as session:
        stored_run = await session.get(PipelineRun, setup.pipeline_run.id)
    assert stored_run is not None
    assert stored_run.jobs_new == 0


@pytest.mark.asyncio
async def test_service_invokes_mapper_and_hash_once_and_persists_canonical_salary(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )
    canonical_job = CanonicalJobInput(
        external_job_id=str(source_record.id),
        title="Canonical platform engineer",
        description="Canonical description",
        location_text="Remote in Germany",
        city="Berlin",
        region="Berlin",
        country_code="DE",
        workplace_type="remote",
        employment_type="full_time",
        salary_min=Decimal("70000.25"),
        salary_max=Decimal("90000.75"),
        salary_currency="EUR",
        salary_period="year",
        source_url=HttpUrl("https://boards.greenhouse.io/example/jobs/1001"),
        source_published_at=OBSERVED_AT,
        source_updated_at=OBSERVED_AT,
        canonical_metadata={"departments": [{"id": 1, "name": "Platform"}]},
    )
    expected_hash = "c" * 64
    mapper = RecordingMapper(canonical_job)
    hasher = RecordingHasher(expected_hash)
    service = NewJobPersistenceService(
        database_context.session_factory,
        mapper=mapper,
        hasher=hasher,
    )

    result = await service.create_new_job(
        PersistNewJobCommand(setup.observation.id, source_record)
    )
    _, version = await load_job_and_version(
        database_context.session_factory,
        result.job_id,
        result.job_version_id,
    )

    assert mapper.calls == [source_record]
    assert hasher.calls == [canonical_job]
    assert version.salary_min == Decimal("70000.25")
    assert version.salary_max == Decimal("90000.75")
    assert version.salary_currency == "EUR"
    assert version.canonical_metadata == {
        "departments": [{"id": 1, "name": "Platform"}]
    }


@pytest.mark.asyncio
async def test_source_record_mismatch_creates_no_job_or_version(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )
    mismatched_record = source_record.model_copy(update={"id": 2002})

    with pytest.raises(SourceObservationRecordMismatchError) as exc_info:
        await NewJobPersistenceService(database_context.session_factory).create_new_job(
            PersistNewJobCommand(setup.observation.id, mismatched_record)
        )

    assert exc_info.value.code == "SOURCE_OBSERVATION_RECORD_MISMATCH"
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_non_greenhouse_observation_is_rejected_before_mapping(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
        provider="other-provider",
    )
    mapper = RecordingMapper(map_greenhouse_job(source_record))

    with pytest.raises(NewJobUnsupportedProviderError) as exc_info:
        await NewJobPersistenceService(
            database_context.session_factory,
            mapper=mapper,
        ).create_new_job(PersistNewJobCommand(setup.observation.id, source_record))

    assert exc_info.value.code == "NEW_JOB_UNSUPPORTED_PROVIDER"
    assert mapper.calls == []
    assert await count_rows(database_context, Job) == 0


@pytest.mark.asyncio
async def test_existing_job_is_deferred_without_creating_version(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )
    async with database_context.session_factory.begin() as session:
        session.add(
            Job(
                company_id=setup.company.id,
                source_connection_id=setup.source_connection.id,
                external_job_id=setup.observation.external_job_id,
                first_seen_at=OBSERVED_AT,
                last_seen_at=OBSERVED_AT,
            )
        )

    with pytest.raises(ExistingJobRequiresComparisonError) as exc_info:
        await NewJobPersistenceService(database_context.session_factory).create_new_job(
            PersistNewJobCommand(setup.observation.id, source_record)
        )

    assert exc_info.value.code == "EXISTING_JOB_REQUIRES_COMPARISON"
    assert await count_rows(database_context, Job) == 1
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_observation_with_existing_version_is_rejected_stably(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )
    canonical_job = map_greenhouse_job(source_record)
    async with database_context.session_factory.begin() as session:
        job = Job(
            company_id=setup.company.id,
            source_connection_id=setup.source_connection.id,
            external_job_id=setup.observation.external_job_id,
            first_seen_at=OBSERVED_AT,
            last_seen_at=OBSERVED_AT,
        )
        session.add(job)
        await session.flush()
        session.add(
            JobVersion(
                job_id=job.id,
                source_observation_id=setup.observation.id,
                version_number=1,
                content_hash=compute_canonical_job_hash(canonical_job),
                title=canonical_job.title,
                description=canonical_job.description,
                location_text=canonical_job.location_text,
                source_url=str(canonical_job.source_url),
                effective_from=OBSERVED_AT,
            )
        )

    with pytest.raises(SourceObservationAlreadyMaterializedError) as exc_info:
        await NewJobPersistenceService(database_context.session_factory).create_new_job(
            PersistNewJobCommand(setup.observation.id, source_record)
        )

    assert exc_info.value.code == "SOURCE_OBSERVATION_ALREADY_MATERIALIZED"
    assert await count_rows(database_context, Job) == 1
    assert await count_rows(database_context, JobVersion) == 1


@pytest.mark.asyncio
async def test_mapping_failure_preserves_observation_without_job(
    database_context: DatabaseContext,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )

    def fail_mapping(_source_record: GreenhouseJob) -> CanonicalJobInput:
        raise ValueError("simulated mapper failure")

    with pytest.raises(SourceRecordNormalizationError) as exc_info:
        await NewJobPersistenceService(
            database_context.session_factory,
            mapper=fail_mapping,
        ).create_new_job(PersistNewJobCommand(setup.observation.id, source_record))

    assert exc_info.value.code == "SOURCE_RECORD_NORMALIZATION_FAILED"
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, JobVersion) == 0
    async with database_context.session_factory() as session:
        assert await session.get(SourceObservation, setup.observation.id) is not None


@pytest.mark.asyncio
async def test_version_failure_rolls_back_flushed_job(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )

    async def fail_version(
        _repository: JobRepository,
        _version: JobVersion,
    ) -> JobVersion:
        raise IntegrityError(
            "INSERT job_versions",
            {},
            ConstraintViolation("simulated_job_version_constraint"),
        )

    monkeypatch.setattr(JobRepository, "add_version", fail_version)

    with pytest.raises(NewJobDatabaseError) as exc_info:
        await NewJobPersistenceService(database_context.session_factory).create_new_job(
            PersistNewJobCommand(setup.observation.id, source_record)
        )

    assert exc_info.value.code == "NEW_JOB_DATABASE_ERROR"
    assert isinstance(exc_info.value.__cause__, IntegrityError)
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_stable_identity_integrity_race_is_translated_and_rolled_back(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_record = fixture_job()
    setup = await create_observation_setup(
        database_context.session_factory,
        source_record,
    )
    original_add_job = JobRepository.add_job

    async def insert_then_report_race(
        repository: JobRepository,
        job: Job,
    ) -> Job:
        await original_add_job(repository, job)
        raise IntegrityError(
            "INSERT jobs",
            {},
            ConstraintViolation("uq_jobs_source_connection_id_external_job_id"),
        )

    monkeypatch.setattr(JobRepository, "add_job", insert_then_report_race)

    with pytest.raises(ExistingJobRequiresComparisonError) as exc_info:
        await NewJobPersistenceService(database_context.session_factory).create_new_job(
            PersistNewJobCommand(setup.observation.id, source_record)
        )

    assert exc_info.value.code == "EXISTING_JOB_REQUIRES_COMPARISON"
    assert isinstance(exc_info.value.__cause__, IntegrityError)
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, JobVersion) == 0


@pytest.mark.asyncio
async def test_missing_observation_has_stable_error(
    database_context: DatabaseContext,
) -> None:
    with pytest.raises(SourceObservationNotFoundError) as exc_info:
        await NewJobPersistenceService(database_context.session_factory).create_new_job(
            PersistNewJobCommand(uuid4(), fixture_job())
        )

    assert exc_info.value.code == "SOURCE_OBSERVATION_NOT_FOUND"
    assert await count_rows(database_context, Job) == 0


def test_job_version_schema_has_no_greenhouse_specific_columns() -> None:
    assert not {
        "internal_job_id",
        "requisition_id",
        "departments",
        "offices",
        "greenhouse_metadata",
    }.intersection(JobVersion.__table__.columns.keys())
