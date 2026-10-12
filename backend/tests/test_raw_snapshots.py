from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.companies.models import Company
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.raw_snapshots.models import RawSnapshot
from app.sources.models import SourceConnection, SourceProvider


async def create_pipeline_run(
    db_session: AsyncSession,
    *,
    source_key: str = "acme",
) -> PipelineRun:
    source = SourceConnection(
        company=Company(name=f"Company {source_key}", slug=source_key),
        provider=SourceProvider.GREENHOUSE.value,
        external_account_key=source_key,
    )
    pipeline_run = PipelineRun(
        source_connection=source,
        status=PipelineRunStatus.RUNNING.value,
        started_at=datetime.now(UTC),
    )
    db_session.add(pipeline_run)
    await db_session.flush()
    return pipeline_run


def build_snapshot(
    pipeline_run_id: UUID,
    *,
    object_key: str,
) -> RawSnapshot:
    return RawSnapshot(
        pipeline_run_id=pipeline_run_id,
        r2_object_key=object_key,
        content_hash="a" * 64,
        content_type="application/json",
        content_length_bytes=1024,
        record_count=42,
        retrieved_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_raw_snapshot_persists_metadata_and_relationships(
    db_session: AsyncSession,
) -> None:
    pipeline_run = await create_pipeline_run(db_session)
    snapshot = build_snapshot(
        pipeline_run.id,
        object_key=f"bronze/greenhouse/run={pipeline_run.id}/jobs.json",
    )
    db_session.add(snapshot)
    await db_session.flush()

    run_id = pipeline_run.id
    snapshot_id = snapshot.id
    db_session.expunge_all()

    loaded_snapshot = (
        await db_session.execute(
            select(RawSnapshot)
            .options(joinedload(RawSnapshot.pipeline_run))
            .where(RawSnapshot.id == snapshot_id)
        )
    ).scalar_one()
    loaded_run = (
        await db_session.execute(
            select(PipelineRun)
            .options(joinedload(PipelineRun.raw_snapshot))
            .where(PipelineRun.id == run_id)
        )
    ).scalar_one()

    assert loaded_snapshot.pipeline_run.id == run_id
    assert loaded_run.raw_snapshot is not None
    assert loaded_run.raw_snapshot.id == snapshot_id
    assert loaded_snapshot.content_hash == "a" * 64
    assert loaded_snapshot.content_length_bytes == 1024
    assert loaded_snapshot.record_count == 42
    assert loaded_snapshot.retrieved_at.tzinfo is not None
    assert loaded_snapshot.created_at.tzinfo is not None


@pytest.mark.asyncio
async def test_only_one_raw_snapshot_is_allowed_per_pipeline_run(
    db_session: AsyncSession,
) -> None:
    pipeline_run = await create_pipeline_run(db_session)
    db_session.add(build_snapshot(pipeline_run.id, object_key="bronze/first.json"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_snapshot(pipeline_run.id, object_key="bronze/second.json")
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_raw_snapshot_object_key_is_unique(
    db_session: AsyncSession,
) -> None:
    first_run = await create_pipeline_run(db_session, source_key="first")
    second_run = await create_pipeline_run(db_session, source_key="second")
    db_session.add(build_snapshot(first_run.id, object_key="bronze/shared.json"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_snapshot(second_run.id, object_key="bronze/shared.json")
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_raw_snapshot_pipeline_foreign_key_is_enforced(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                build_snapshot(uuid4(), object_key="bronze/missing-run.json")
            )
            await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("field_name", ["content_length_bytes", "record_count"])
async def test_raw_snapshot_counts_cannot_be_negative(
    db_session: AsyncSession,
    field_name: str,
) -> None:
    pipeline_run = await create_pipeline_run(db_session)
    snapshot = build_snapshot(pipeline_run.id, object_key="bronze/invalid.json")
    setattr(snapshot, field_name, -1)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(snapshot)
            await db_session.flush()
