from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.companies.models import Company
from app.jobs.models import Job, JobVersion
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.models import SourceConnection, SourceProvider

OBSERVED_AT = datetime(2026, 10, 6, 9, tzinfo=UTC)


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


async def create_run_and_snapshot(
    db_session: AsyncSession,
    source: SourceConnection,
    *,
    observed_at: datetime = OBSERVED_AT,
) -> tuple[PipelineRun, RawSnapshot]:
    pipeline_run = PipelineRun(
        source_connection=source,
        status=PipelineRunStatus.COMPLETED.value,
        started_at=observed_at,
        completed_at=observed_at,
    )
    db_session.add(pipeline_run)
    await db_session.flush()
    snapshot = RawSnapshot(
        pipeline_run=pipeline_run,
        r2_object_key=f"bronze/test/run={pipeline_run.id}/jobs.json",
        content_hash="a" * 64,
        content_type="application/json",
        record_count=1,
        retrieved_at=observed_at,
    )
    db_session.add(snapshot)
    await db_session.flush()
    return pipeline_run, snapshot


def build_observation(
    source: SourceConnection,
    pipeline_run: PipelineRun,
    snapshot: RawSnapshot,
    *,
    external_job_id: str = "1001",
    observed_at: datetime = OBSERVED_AT,
) -> SourceObservation:
    return SourceObservation(
        pipeline_run=pipeline_run,
        source_connection=source,
        raw_snapshot=snapshot,
        external_job_id=external_job_id,
        raw_record_locator="jobs[0]",
        source_content_hash="b" * 64,
        observed_at=observed_at,
        source_metadata={"department": "Engineering"},
    )


def build_job(
    company: Company,
    source: SourceConnection,
    *,
    external_job_id: str = "1001",
) -> Job:
    return Job(
        company=company,
        source_connection=source,
        external_job_id=external_job_id,
        first_seen_at=OBSERVED_AT,
        last_seen_at=OBSERVED_AT,
    )


def build_version(
    job: Job,
    observation: SourceObservation | None,
    *,
    version_number: int = 1,
    content_hash: str = "c" * 64,
    is_current: bool = True,
    effective_to: datetime | None = None,
) -> JobVersion:
    version = JobVersion(
        job=job,
        version_number=version_number,
        content_hash=content_hash,
        title="Backend Engineer",
        source_url="https://boards.greenhouse.io/example/jobs/1001",
        effective_from=OBSERVED_AT,
        effective_to=effective_to,
        is_current=is_current,
    )
    if observation is not None:
        version.source_observation = observation
    return version


@pytest.mark.asyncio
async def test_source_observation_persists_provenance_and_relationships(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    observation = build_observation(source, pipeline_run, snapshot)
    db_session.add(observation)
    await db_session.flush()
    observation_id = observation.id
    run_id = pipeline_run.id
    snapshot_id = snapshot.id
    source_id = source.id
    db_session.expunge_all()

    loaded = (
        await db_session.execute(
            select(SourceObservation)
            .options(
                joinedload(SourceObservation.pipeline_run),
                joinedload(SourceObservation.source_connection),
                joinedload(SourceObservation.raw_snapshot),
                joinedload(SourceObservation.job_version),
            )
            .where(SourceObservation.id == observation_id)
        )
    ).scalar_one()
    loaded_run = (
        await db_session.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.source_observations))
            .where(PipelineRun.id == run_id)
        )
    ).scalar_one()
    loaded_snapshot = (
        await db_session.execute(
            select(RawSnapshot)
            .options(selectinload(RawSnapshot.source_observations))
            .where(RawSnapshot.id == snapshot_id)
        )
    ).scalar_one()
    loaded_source = (
        await db_session.execute(
            select(SourceConnection)
            .options(selectinload(SourceConnection.source_observations))
            .where(SourceConnection.id == source_id)
        )
    ).scalar_one()

    assert loaded.pipeline_run.id == run_id
    assert loaded.source_connection.id == source_id
    assert loaded.raw_snapshot.id == snapshot_id
    assert loaded.external_job_id == "1001"
    assert loaded.raw_record_locator == "jobs[0]"
    assert loaded.source_content_hash == "b" * 64
    assert loaded.source_metadata == {"department": "Engineering"}
    assert loaded.observed_at == OBSERVED_AT
    assert loaded.created_at.tzinfo is not None
    assert loaded.job_version is None
    assert [item.id for item in loaded_run.source_observations] == [observation_id]
    assert [item.id for item in loaded_snapshot.source_observations] == [observation_id]
    assert [item.id for item in loaded_source.source_observations] == [observation_id]


@pytest.mark.asyncio
async def test_external_job_id_is_unique_within_one_pipeline_run(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    db_session.add(build_observation(source, pipeline_run, snapshot))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(build_observation(source, pipeline_run, snapshot))
            await db_session.flush()


@pytest.mark.asyncio
async def test_same_external_job_id_can_be_observed_in_different_runs(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    first_run, first_snapshot = await create_run_and_snapshot(db_session, source)
    second_run, second_snapshot = await create_run_and_snapshot(
        db_session,
        source,
        observed_at=OBSERVED_AT + timedelta(hours=1),
    )
    db_session.add_all(
        [
            build_observation(source, first_run, first_snapshot),
            build_observation(
                source,
                second_run,
                second_snapshot,
                observed_at=OBSERVED_AT + timedelta(hours=1),
            ),
        ]
    )

    await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_parent",
    ["pipeline_run", "source_connection", "raw_snapshot"],
)
async def test_source_observation_foreign_keys_are_enforced(
    db_session: AsyncSession,
    missing_parent: str,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    foreign_keys = {
        "pipeline_run_id": pipeline_run.id,
        "source_connection_id": source.id,
        "raw_snapshot_id": snapshot.id,
    }
    foreign_keys[f"{missing_parent}_id"] = uuid4()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SourceObservation(
                    **foreign_keys,
                    external_job_id="1001",
                    observed_at=OBSERVED_AT,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_source_content_hash_is_optional_but_validated_when_present(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    observation = SourceObservation(
        pipeline_run=pipeline_run,
        source_connection=source,
        raw_snapshot=snapshot,
        external_job_id="1001",
        observed_at=OBSERVED_AT,
    )
    db_session.add(observation)
    await db_session.flush()
    await db_session.refresh(observation)

    assert observation.source_content_hash is None
    assert observation.raw_record_locator is None
    assert observation.source_metadata == {}

    other_run, other_snapshot = await create_run_and_snapshot(
        db_session,
        source,
        observed_at=OBSERVED_AT + timedelta(hours=1),
    )
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            invalid = build_observation(source, other_run, other_snapshot)
            invalid.source_content_hash = "not-a-sha256"
            db_session.add(invalid)
            await db_session.flush()


@pytest.mark.asyncio
async def test_job_version_requires_a_source_observation(
    db_session: AsyncSession,
) -> None:
    company, source = await create_source(db_session)
    job = build_job(company, source)
    db_session.add(job)
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(build_version(job, None))
            await db_session.flush()


@pytest.mark.asyncio
async def test_one_source_observation_creates_at_most_one_job_version(
    db_session: AsyncSession,
) -> None:
    company, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    observation = build_observation(source, pipeline_run, snapshot)
    job = build_job(company, source)
    db_session.add(
        build_version(
            job,
            observation,
            is_current=False,
            effective_to=OBSERVED_AT + timedelta(hours=1),
        )
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_version(
                    job,
                    observation,
                    version_number=2,
                    content_hash="d" * 64,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_version_traces_to_snapshot_run_source_and_company(
    db_session: AsyncSession,
) -> None:
    company, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    observation = build_observation(source, pipeline_run, snapshot)
    version = build_version(build_job(company, source), observation)
    db_session.add(version)
    await db_session.flush()
    version_id = version.id
    db_session.expunge_all()

    loaded = (
        await db_session.execute(
            select(JobVersion)
            .options(
                joinedload(JobVersion.source_observation)
                .joinedload(SourceObservation.raw_snapshot)
                .joinedload(RawSnapshot.pipeline_run)
                .joinedload(PipelineRun.source_connection)
                .joinedload(SourceConnection.company)
            )
            .where(JobVersion.id == version_id)
        )
    ).scalar_one()

    loaded_observation = loaded.source_observation
    assert loaded_observation.external_job_id == "1001"
    assert loaded_observation.raw_snapshot.r2_object_key.endswith("/jobs.json")
    assert loaded_observation.raw_snapshot.pipeline_run.id == pipeline_run.id
    assert (
        loaded_observation.raw_snapshot.pipeline_run.source_connection.id == source.id
    )
    assert (
        loaded_observation.raw_snapshot.pipeline_run.source_connection.company.id
        == company.id
    )


@pytest.mark.asyncio
async def test_unchanged_record_creates_an_observation_without_an_extra_version(
    db_session: AsyncSession,
) -> None:
    company, source = await create_source(db_session)
    job = build_job(company, source)
    db_session.add(job)
    await db_session.flush()
    first_run, first_snapshot = await create_run_and_snapshot(db_session, source)
    first_observation = build_observation(source, first_run, first_snapshot)
    db_session.add(build_version(job, first_observation))
    await db_session.flush()

    second_run, second_snapshot = await create_run_and_snapshot(
        db_session,
        source,
        observed_at=OBSERVED_AT + timedelta(hours=1),
    )
    db_session.add(
        build_observation(
            source,
            second_run,
            second_snapshot,
            observed_at=OBSERVED_AT + timedelta(hours=1),
        )
    )
    await db_session.flush()

    observation_count = await db_session.scalar(
        select(func.count())
        .select_from(SourceObservation)
        .where(SourceObservation.source_connection_id == source.id)
    )
    version_count = await db_session.scalar(
        select(func.count()).select_from(JobVersion).where(JobVersion.job_id == job.id)
    )

    assert observation_count == 2
    assert version_count == 1


@pytest.mark.asyncio
async def test_observation_delete_is_restricted_while_a_version_references_it(
    db_session: AsyncSession,
) -> None:
    company, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    observation = build_observation(source, pipeline_run, snapshot)
    db_session.add(build_version(build_job(company, source), observation))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                delete(SourceObservation).where(SourceObservation.id == observation.id)
            )
