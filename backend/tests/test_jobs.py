from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.companies.models import Company
from app.jobs.hashing import compute_canonical_job_hash
from app.jobs.models import Job, JobLifecycleStatus, JobVersion
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.sources.greenhouse.validation import parse_greenhouse_response
from app.sources.models import SourceConnection, SourceProvider

OBSERVED_AT = datetime(2026, 10, 6, 9, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "greenhouse"


def fixture_text(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


async def create_source(
    db_session: AsyncSession,
    *,
    key: str = "acme",
) -> tuple[Company, SourceConnection]:
    company = Company(name=f"Company {key}", slug=key)
    source = SourceConnection(
        company=company,
        provider=SourceProvider.GREENHOUSE.value,
        external_account_key=key,
    )
    db_session.add(source)
    await db_session.flush()
    return company, source


async def create_job(
    db_session: AsyncSession,
    *,
    key: str = "acme",
    external_job_id: str = "1001",
) -> Job:
    company, source = await create_source(db_session, key=key)
    job = Job(
        company=company,
        source_connection=source,
        external_job_id=external_job_id,
        first_seen_at=OBSERVED_AT,
        last_seen_at=OBSERVED_AT,
    )
    db_session.add(job)
    await db_session.flush()
    return job


async def create_observation(
    db_session: AsyncSession,
    job: Job,
    *,
    observed_at: datetime = OBSERVED_AT,
) -> SourceObservation:
    pipeline_run = PipelineRun(
        source_connection=job.source_connection,
        status=PipelineRunStatus.COMPLETED.value,
        started_at=observed_at,
        completed_at=observed_at,
    )
    db_session.add(pipeline_run)
    await db_session.flush()
    snapshot = RawSnapshot(
        pipeline_run=pipeline_run,
        r2_object_key=f"bronze/test/run={pipeline_run.id}/jobs.json",
        content_hash="f" * 64,
        content_type="application/json",
        record_count=1,
        retrieved_at=observed_at,
    )
    observation = SourceObservation(
        pipeline_run=pipeline_run,
        source_connection=job.source_connection,
        raw_snapshot=snapshot,
        external_job_id=job.external_job_id,
        raw_record_locator="jobs[0]",
        observed_at=observed_at,
    )
    db_session.add(observation)
    await db_session.flush()
    return observation


def build_version(
    job: Job,
    source_observation: SourceObservation,
    *,
    version_number: int = 1,
    content_hash: str = "a" * 64,
    is_current: bool = True,
    effective_from: datetime = OBSERVED_AT,
    effective_to: datetime | None = None,
) -> JobVersion:
    return JobVersion(
        job=job,
        source_observation=source_observation,
        version_number=version_number,
        content_hash=content_hash,
        title="Backend Engineer",
        description="<p>Build APIs.</p>",
        location_text="Berlin, Germany",
        source_url="https://boards.greenhouse.io/example/jobs/1001",
        effective_from=effective_from,
        effective_to=effective_to,
        is_current=is_current,
    )


@pytest.mark.asyncio
async def test_job_persists_identity_lifecycle_and_relationships(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    job_id = job.id
    company_id = job.company_id
    source_id = job.source_connection_id
    db_session.expunge_all()

    loaded = (
        await db_session.execute(
            select(Job)
            .options(
                joinedload(Job.company),
                joinedload(Job.source_connection),
                selectinload(Job.versions),
            )
            .where(Job.id == job_id)
        )
    ).scalar_one()
    loaded_company = (
        await db_session.execute(
            select(Company)
            .options(selectinload(Company.jobs))
            .where(Company.id == company_id)
        )
    ).scalar_one()
    loaded_source = (
        await db_session.execute(
            select(SourceConnection)
            .options(selectinload(SourceConnection.jobs))
            .where(SourceConnection.id == source_id)
        )
    ).scalar_one()

    assert loaded.external_job_id == "1001"
    assert loaded.company.id == company_id
    assert loaded.source_connection.id == source_id
    assert loaded.first_seen_at == OBSERVED_AT
    assert loaded.last_seen_at == OBSERVED_AT
    assert loaded.lifecycle_status == JobLifecycleStatus.OBSERVED.value
    assert loaded.no_longer_observed_at is None
    assert loaded.reappeared_at is None
    assert loaded.versions == []
    assert [item.id for item in loaded_company.jobs] == [job_id]
    assert [item.id for item in loaded_source.jobs] == [job_id]
    assert loaded.created_at.tzinfo is not None
    assert loaded.updated_at.tzinfo is not None


@pytest.mark.asyncio
async def test_source_and_external_id_form_stable_job_identity(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Job(
                    company_id=job.company_id,
                    source_connection_id=job.source_connection_id,
                    external_job_id=job.external_job_id,
                    first_seen_at=OBSERVED_AT,
                    last_seen_at=OBSERVED_AT,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_same_external_id_is_allowed_on_different_sources(
    db_session: AsyncSession,
) -> None:
    first = await create_job(db_session, key="first", external_job_id="shared-id")
    second = await create_job(db_session, key="second", external_job_id="shared-id")

    assert first.source_connection_id != second.source_connection_id


@pytest.mark.asyncio
async def test_job_version_persists_canonical_fields_decimal_and_jsonb(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    observation = await create_observation(db_session, job)
    version = build_version(job, observation)
    version.city = "Berlin"
    version.country_code = "DE"
    version.workplace_type = "hybrid"
    version.employment_type = "full_time"
    version.salary_min = Decimal("65000.00")
    version.salary_max = Decimal("80000.00")
    version.salary_currency = "EUR"
    version.salary_period = "year"
    version.source_published_at = OBSERVED_AT - timedelta(days=7)
    version.source_updated_at = OBSERVED_AT - timedelta(hours=1)
    version.canonical_metadata = {"departments": [{"id": 1, "name": "Engineering"}]}
    db_session.add(version)
    await db_session.flush()
    await db_session.refresh(version)

    assert version.version_number == 1
    assert version.content_hash == "a" * 64
    assert version.salary_min == Decimal("65000.00")
    assert version.salary_max == Decimal("80000.00")
    assert version.canonical_metadata == {
        "departments": [{"id": 1, "name": "Engineering"}]
    }
    assert version.source_published_at is not None
    assert version.source_published_at.tzinfo is not None
    assert version.source_updated_at is not None
    assert version.source_updated_at.tzinfo is not None
    assert version.effective_from.tzinfo is not None
    assert version.effective_to is None
    assert version.is_current is True
    assert version.created_at.tzinfo is not None


@pytest.mark.asyncio
async def test_version_number_is_unique_within_one_job(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    first_observation = await create_observation(db_session, job)
    db_session.add(
        build_version(
            job,
            first_observation,
            content_hash="a" * 64,
            is_current=False,
            effective_to=OBSERVED_AT + timedelta(hours=1),
        )
    )
    await db_session.flush()
    second_observation = await create_observation(
        db_session,
        job,
        observed_at=OBSERVED_AT + timedelta(hours=2),
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_version(
                    job,
                    second_observation,
                    version_number=1,
                    content_hash="b" * 64,
                    is_current=False,
                    effective_to=OBSERVED_AT + timedelta(hours=2),
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_version_number_and_content_hash_may_repeat_across_jobs(
    db_session: AsyncSession,
) -> None:
    first_job = await create_job(db_session, key="first")
    second_job = await create_job(db_session, key="second")
    first_observation = await create_observation(db_session, first_job)
    second_observation = await create_observation(db_session, second_job)
    db_session.add_all(
        [
            build_version(first_job, first_observation, content_hash="a" * 64),
            build_version(second_job, second_observation, content_hash="a" * 64),
        ]
    )

    await db_session.flush()


@pytest.mark.asyncio
async def test_partial_unique_index_allows_only_one_current_version(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    first_observation = await create_observation(db_session, job)
    db_session.add(build_version(job, first_observation))
    await db_session.flush()
    second_observation = await create_observation(
        db_session,
        job,
        observed_at=OBSERVED_AT + timedelta(hours=1),
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_version(
                    job,
                    second_observation,
                    version_number=2,
                    content_hash="b" * 64,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_historical_and_current_versions_can_coexist(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    transition_at = OBSERVED_AT + timedelta(days=1)
    first_observation = await create_observation(db_session, job)
    second_observation = await create_observation(
        db_session,
        job,
        observed_at=transition_at,
    )
    db_session.add_all(
        [
            build_version(
                job,
                first_observation,
                is_current=False,
                effective_to=transition_at,
            ),
            build_version(
                job,
                second_observation,
                version_number=2,
                content_hash="b" * 64,
                effective_from=transition_at,
            ),
        ]
    )
    await db_session.flush()
    job_id = job.id
    db_session.expunge_all()

    loaded = (
        await db_session.execute(
            select(Job).options(selectinload(Job.versions)).where(Job.id == job_id)
        )
    ).scalar_one()

    assert [version.version_number for version in loaded.versions] == [1, 2]
    assert loaded.versions[0].is_current is False
    assert loaded.versions[0].effective_to == transition_at
    assert loaded.versions[1].is_current is True
    assert loaded.versions[1].effective_to is None


@pytest.mark.asyncio
async def test_duplicate_content_hash_is_rejected_for_same_job(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    first_observation = await create_observation(db_session, job)
    db_session.add(
        build_version(
            job,
            first_observation,
            content_hash="a" * 64,
            is_current=False,
            effective_to=OBSERVED_AT + timedelta(hours=1),
        )
    )
    await db_session.flush()
    second_observation = await create_observation(
        db_session,
        job,
        observed_at=OBSERVED_AT + timedelta(hours=1),
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_version(
                    job,
                    second_observation,
                    version_number=2,
                    content_hash="a" * 64,
                    effective_from=OBSERVED_AT + timedelta(hours=1),
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_nullable_salary_and_metadata_default_persist(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    observation = await create_observation(db_session, job)
    version = build_version(job, observation)
    db_session.add(version)
    await db_session.flush()
    await db_session.refresh(version)

    assert version.salary_min is None
    assert version.salary_max is None
    assert version.salary_currency is None
    assert version.salary_period is None
    assert version.canonical_metadata == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "version_changes",
    [
        {"version_number": 0},
        {"content_hash": "not-a-sha256"},
        {"salary_min": Decimal("-1.00")},
        {"salary_min": Decimal("80000.00"), "salary_max": Decimal("65000.00")},
    ],
)
async def test_invalid_version_values_are_rejected_by_database(
    db_session: AsyncSession,
    version_changes: dict[str, object],
) -> None:
    job = await create_job(db_session)
    observation = await create_observation(db_session, job)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            version = build_version(job, observation)
            for field_name, value in version_changes.items():
                setattr(version, field_name, value)
            db_session.add(version)
            await db_session.flush()


@pytest.mark.asyncio
async def test_invalid_effective_range_is_rejected(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    observation = await create_observation(db_session, job)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_version(
                    job,
                    observation,
                    is_current=False,
                    effective_from=OBSERVED_AT,
                    effective_to=OBSERVED_AT - timedelta(seconds=1),
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_job_delete_is_restricted_while_versions_exist(
    db_session: AsyncSession,
) -> None:
    job = await create_job(db_session)
    observation = await create_observation(db_session, job)
    db_session.add(build_version(job, observation))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(delete(Job).where(Job.id == job.id))


@pytest.mark.asyncio
async def test_greenhouse_mapping_and_hash_fit_job_version_storage(
    db_session: AsyncSession,
) -> None:
    validation = parse_greenhouse_response(fixture_text("jobs_v1.json"))
    source_job: GreenhouseJob = validation.valid_records[0]
    canonical = map_greenhouse_job(source_job)
    content_hash = compute_canonical_job_hash(canonical)
    company, source = await create_source(db_session, key="fixture-company")
    job = Job(
        company=company,
        source_connection=source,
        external_job_id=canonical.external_job_id,
        first_seen_at=OBSERVED_AT,
        last_seen_at=OBSERVED_AT,
    )
    db_session.add(job)
    await db_session.flush()
    observation = await create_observation(db_session, job)
    version = JobVersion(
        job=job,
        source_observation=observation,
        version_number=1,
        content_hash=content_hash,
        title=canonical.title,
        description=canonical.description,
        location_text=canonical.location_text,
        city=canonical.city,
        region=canonical.region,
        country_code=canonical.country_code,
        workplace_type=canonical.workplace_type,
        employment_type=canonical.employment_type,
        salary_min=canonical.salary_min,
        salary_max=canonical.salary_max,
        salary_currency=canonical.salary_currency,
        salary_period=canonical.salary_period,
        source_url=str(canonical.source_url),
        source_published_at=canonical.source_published_at,
        source_updated_at=canonical.source_updated_at,
        effective_from=OBSERVED_AT,
        canonical_metadata=cast(dict[str, object], canonical.canonical_metadata),
    )
    db_session.add(version)
    await db_session.flush()
    version_id = version.id
    db_session.expunge_all()

    loaded = (
        await db_session.execute(
            select(JobVersion)
            .options(joinedload(JobVersion.job))
            .where(JobVersion.id == version_id)
        )
    ).scalar_one()

    assert loaded.job.external_job_id == "1001"
    assert loaded.content_hash == content_hash
    assert loaded.title == canonical.title
    assert loaded.description == canonical.description
    assert loaded.location_text == canonical.location_text
    assert loaded.source_url == str(canonical.source_url)
    assert loaded.source_updated_at == canonical.source_updated_at
    assert loaded.canonical_metadata == canonical.canonical_metadata
