from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.companies.models import Company
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.sources.models import SourceConnection, SourceProvider


async def create_source(db_session: AsyncSession) -> SourceConnection:
    source = SourceConnection(
        company=Company(name="Acme", slug="acme"),
        provider=SourceProvider.GREENHOUSE.value,
        external_account_key="acme",
    )
    db_session.add(source)
    await db_session.flush()
    return source


@pytest.mark.asyncio
async def test_pipeline_run_persists_defaults_and_relationships(
    db_session: AsyncSession,
) -> None:
    source = await create_source(db_session)
    started_at = datetime.now(UTC)
    pipeline_run = PipelineRun(
        source_connection=source,
        status=PipelineRunStatus.RUNNING.value,
        started_at=started_at,
    )
    db_session.add(pipeline_run)
    await db_session.flush()

    source_id = source.id
    run_id = pipeline_run.id
    db_session.expunge_all()

    loaded_run = (
        await db_session.execute(
            select(PipelineRun)
            .options(joinedload(PipelineRun.source_connection))
            .where(PipelineRun.id == run_id)
        )
    ).scalar_one()
    loaded_source = (
        await db_session.execute(
            select(SourceConnection)
            .options(selectinload(SourceConnection.pipeline_runs))
            .where(SourceConnection.id == source_id)
        )
    ).scalar_one()

    assert loaded_run.source_connection.id == source_id
    assert [item.id for item in loaded_source.pipeline_runs] == [run_id]
    assert loaded_run.status == PipelineRunStatus.RUNNING.value
    assert loaded_run.started_at == started_at
    assert loaded_run.completed_at is None
    assert loaded_run.records_fetched == 0
    assert loaded_run.records_valid == 0
    assert loaded_run.records_quarantined == 0
    assert loaded_run.jobs_new == 0
    assert loaded_run.jobs_changed == 0
    assert loaded_run.jobs_unchanged == 0
    assert loaded_run.created_at.tzinfo is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric_name",
    [
        "records_fetched",
        "records_valid",
        "records_quarantined",
        "jobs_new",
        "jobs_changed",
        "jobs_unchanged",
    ],
)
async def test_pipeline_metrics_cannot_be_negative(
    db_session: AsyncSession,
    metric_name: str,
) -> None:
    source = await create_source(db_session)
    pipeline_run = PipelineRun(
        source_connection_id=source.id,
        status=PipelineRunStatus.PENDING.value,
        started_at=datetime.now(UTC),
    )
    setattr(pipeline_run, metric_name, -1)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(pipeline_run)
            await db_session.flush()


@pytest.mark.asyncio
async def test_failed_run_can_store_safe_error_information(
    db_session: AsyncSession,
) -> None:
    source = await create_source(db_session)
    completed_at = datetime.now(UTC)
    pipeline_run = PipelineRun(
        source_connection_id=source.id,
        status=PipelineRunStatus.FAILED.value,
        started_at=completed_at,
        completed_at=completed_at,
        error_code="SOURCE_REQUEST_FAILED",
        error_summary="Source request timed out after configured retries.",
    )
    db_session.add(pipeline_run)

    await db_session.flush()

    assert pipeline_run.error_code == "SOURCE_REQUEST_FAILED"
    assert pipeline_run.error_summary is not None
    assert pipeline_run.records_fetched == 0
