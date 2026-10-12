from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.companies.models import Company
from app.config import get_settings
from app.database.engine import create_database_engine
from app.ingestion.locking import PostgresSourceRunLock
from app.pipeline_runs.errors import (
    PipelineRunAlreadyFinalizedError,
    PipelineRunInvalidTransitionError,
    SourceConnectionInactiveError,
    SourceSyncAlreadyRunningError,
)
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.pipeline_runs.schemas import PipelineMetrics
from app.pipeline_runs.service import PipelineRunService
from app.sources.models import SourceConnection, SourceProvider


@dataclass(frozen=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]


class SequenceClock:
    def __init__(self, timestamps: Sequence[datetime]) -> None:
        self._timestamps = iter(timestamps)

    def __call__(self) -> datetime:
        return next(self._timestamps)


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

        try:
            yield DatabaseContext(engine, connection, session_factory)
        finally:
            if transaction.is_active:
                await transaction.rollback()

    await engine.dispose()


async def create_source(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    is_active: bool = True,
    last_successful_sync_at: datetime | None = None,
) -> SourceConnection:
    suffix = uuid4().hex
    async with session_factory.begin() as session:
        source = SourceConnection(
            company=Company(name=f"Company {suffix}", slug=f"company-{suffix}"),
            provider=SourceProvider.GREENHOUSE.value,
            external_account_key=f"board-{suffix}",
            is_active=is_active,
            last_successful_sync_at=last_successful_sync_at,
        )
        session.add(source)
        await session.flush()
    return source


async def load_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: UUID,
) -> PipelineRun:
    async with session_factory() as session:
        return (
            await session.scalars(select(PipelineRun).where(PipelineRun.id == run_id))
        ).one()


async def load_source(
    session_factory: async_sessionmaker[AsyncSession],
    source_id: UUID,
) -> SourceConnection:
    async with session_factory() as session:
        return (
            await session.scalars(
                select(SourceConnection).where(SourceConnection.id == source_id)
            )
        ).one()


async def count_runs(
    session_factory: async_sessionmaker[AsyncSession],
    source_id: UUID,
) -> int:
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(PipelineRun)
            .where(PipelineRun.source_connection_id == source_id)
        )
    assert count is not None
    return count


@pytest.mark.asyncio
async def test_start_creates_running_run_and_updates_last_attempted(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    requested_at = datetime(2026, 1, 2, 8, 59, tzinfo=UTC)
    started_at = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    service = PipelineRunService(
        database_context.session_factory,
        clock=SequenceClock([requested_at, started_at]),
    )

    run = await service.start(source.id)
    stored_run = await load_run(database_context.session_factory, run.id)
    stored_source = await load_source(database_context.session_factory, source.id)

    assert stored_run.status == PipelineRunStatus.RUNNING.value
    assert stored_run.started_at == started_at
    assert stored_run.completed_at is None
    assert stored_run.records_fetched == 0
    assert stored_source.last_attempted_sync_at == started_at
    assert stored_source.last_successful_sync_at is None


@pytest.mark.asyncio
async def test_inactive_source_does_not_create_run(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(
        database_context.session_factory,
        is_active=False,
    )
    service = PipelineRunService(database_context.session_factory)

    with pytest.raises(SourceConnectionInactiveError) as exc_info:
        await service.start(source.id)

    assert exc_info.value.code == "SOURCE_CONNECTION_INACTIVE"
    assert await count_runs(database_context.session_factory, source.id) == 0
    stored_source = await load_source(database_context.session_factory, source.id)
    assert stored_source.last_attempted_sync_at is None


@pytest.mark.asyncio
async def test_lock_contention_does_not_create_duplicate_run(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    service = PipelineRunService(database_context.session_factory)
    source_lock = PostgresSourceRunLock(database_context.engine)

    async with source_lock.hold(source.id):
        await service.start(source.id)
        attempted_before_contention = (
            await load_source(database_context.session_factory, source.id)
        ).last_attempted_sync_at

        with pytest.raises(SourceSyncAlreadyRunningError):
            async with source_lock.hold(source.id):
                await service.start(source.id)

    assert await count_runs(database_context.session_factory, source.id) == 1
    stored_source = await load_source(database_context.session_factory, source.id)
    assert stored_source.last_attempted_sync_at == attempted_before_contention


@pytest.mark.asyncio
async def test_different_sources_can_start_under_independent_locks(
    database_context: DatabaseContext,
) -> None:
    source_a = await create_source(database_context.session_factory)
    source_b = await create_source(database_context.session_factory)
    service = PipelineRunService(database_context.session_factory)
    source_lock = PostgresSourceRunLock(database_context.engine)

    async with source_lock.hold(source_a.id):
        run_a = await service.start(source_a.id)
        async with source_lock.hold(source_b.id):
            run_b = await service.start(source_b.id)

    assert run_a.source_connection_id == source_a.id
    assert run_b.source_connection_id == source_b.id


@pytest.mark.asyncio
async def test_new_run_can_start_after_successful_lock_scope_exits(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    service = PipelineRunService(database_context.session_factory)
    source_lock = PostgresSourceRunLock(database_context.engine)

    async with source_lock.hold(source.id):
        first_run = await service.start(source.id)
        await service.complete(first_run.id, PipelineMetrics())

    async with source_lock.hold(source.id):
        second_run = await service.start(source.id)

    assert second_run.id != first_run.id
    assert await count_runs(database_context.session_factory, source.id) == 2


@pytest.mark.asyncio
async def test_new_run_can_start_after_lock_scope_raises(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    service = PipelineRunService(database_context.session_factory)
    source_lock = PostgresSourceRunLock(database_context.engine)

    with pytest.raises(RuntimeError, match="simulated orchestration failure"):
        async with source_lock.hold(source.id):
            await service.start(source.id)
            raise RuntimeError("simulated orchestration failure")

    async with source_lock.hold(source.id):
        second_run = await service.start(source.id)

    assert second_run.source_connection_id == source.id
    assert await count_runs(database_context.session_factory, source.id) == 2


@pytest.mark.asyncio
async def test_complete_persists_metrics_and_success_timestamp(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    base_time = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    completed_at = base_time + timedelta(minutes=2)
    service = PipelineRunService(
        database_context.session_factory,
        clock=SequenceClock(
            [base_time - timedelta(seconds=1), base_time, completed_at]
        ),
    )
    metrics = PipelineMetrics(
        records_fetched=12,
        records_valid=12,
        jobs_new=4,
        jobs_changed=3,
        jobs_unchanged=5,
    )

    run = await service.start(source.id)
    await service.complete(run.id, metrics)
    stored_run = await load_run(database_context.session_factory, run.id)
    stored_source = await load_source(database_context.session_factory, source.id)

    assert stored_run.status == PipelineRunStatus.COMPLETED.value
    assert stored_run.completed_at == completed_at
    assert stored_run.records_fetched == 12
    assert stored_run.records_valid == 12
    assert stored_run.records_quarantined == 0
    assert stored_run.jobs_new == 4
    assert stored_run.jobs_changed == 3
    assert stored_run.jobs_unchanged == 5
    assert stored_run.error_code is None
    assert stored_run.error_summary is None
    assert stored_source.last_successful_sync_at == completed_at


@pytest.mark.asyncio
async def test_complete_with_errors_counts_as_successful_sync(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    base_time = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    completed_at = base_time + timedelta(minutes=2)
    service = PipelineRunService(
        database_context.session_factory,
        clock=SequenceClock(
            [base_time - timedelta(seconds=1), base_time, completed_at]
        ),
    )
    metrics = PipelineMetrics(
        records_fetched=12,
        records_valid=10,
        records_quarantined=2,
        jobs_new=10,
    )

    run = await service.start(source.id)
    await service.complete_with_errors(run.id, metrics)
    stored_run = await load_run(database_context.session_factory, run.id)
    stored_source = await load_source(database_context.session_factory, source.id)

    assert stored_run.status == PipelineRunStatus.COMPLETED_WITH_ERRORS.value
    assert stored_run.records_quarantined == 2
    assert stored_run.completed_at == completed_at
    assert stored_source.last_successful_sync_at == completed_at


@pytest.mark.asyncio
async def test_fail_preserves_known_metrics_without_advancing_success_timestamp(
    database_context: DatabaseContext,
) -> None:
    previous_success = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    source = await create_source(
        database_context.session_factory,
        last_successful_sync_at=previous_success,
    )
    base_time = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    failed_at = base_time + timedelta(minutes=1)
    service = PipelineRunService(
        database_context.session_factory,
        clock=SequenceClock([base_time - timedelta(seconds=1), base_time, failed_at]),
    )

    run = await service.start(source.id)
    await service.fail(
        run.id,
        error_code="SOURCE_REQUEST_FAILED",
        error_summary="Source request timed out after configured retries.",
        metrics=PipelineMetrics(records_fetched=7, records_valid=2),
    )
    stored_run = await load_run(database_context.session_factory, run.id)
    stored_source = await load_source(database_context.session_factory, source.id)

    assert stored_run.status == PipelineRunStatus.FAILED.value
    assert stored_run.completed_at == failed_at
    assert stored_run.error_code == "SOURCE_REQUEST_FAILED"
    assert stored_run.error_summary == (
        "Source request timed out after configured retries."
    )
    assert stored_run.records_fetched == 7
    assert stored_run.records_valid == 2
    assert stored_source.last_successful_sync_at == previous_success


@pytest.mark.asyncio
async def test_terminal_run_cannot_transition_back_to_running(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    service = PipelineRunService(database_context.session_factory)
    run = await service.start(source.id)
    await service.complete(run.id, PipelineMetrics())

    with pytest.raises(PipelineRunAlreadyFinalizedError) as exc_info:
        await service.mark_running(run.id)

    assert exc_info.value.code == "PIPELINE_ALREADY_FINALIZED"


@pytest.mark.asyncio
async def test_pending_run_cannot_be_finalized(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    async with database_context.session_factory.begin() as session:
        run = PipelineRun(
            source_connection_id=source.id,
            status=PipelineRunStatus.PENDING.value,
            started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.flush()

    service = PipelineRunService(database_context.session_factory)

    with pytest.raises(PipelineRunInvalidTransitionError) as exc_info:
        await service.complete(run.id, PipelineMetrics())

    assert exc_info.value.code == "PIPELINE_INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_double_finalization_is_rejected_without_changing_result(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context.session_factory)
    service = PipelineRunService(database_context.session_factory)
    original_metrics = PipelineMetrics(records_fetched=3, jobs_new=3)
    run = await service.start(source.id)
    completed = await service.complete(run.id, original_metrics)

    with pytest.raises(PipelineRunAlreadyFinalizedError):
        await service.fail(
            run.id,
            error_code="LATE_FAILURE",
            error_summary="This must not overwrite the completed run.",
        )

    stored_run = await load_run(database_context.session_factory, run.id)
    assert stored_run.status == PipelineRunStatus.COMPLETED.value
    assert stored_run.completed_at == completed.completed_at
    assert stored_run.records_fetched == 3
    assert stored_run.jobs_new == 3
    assert stored_run.error_code is None


def test_pipeline_metrics_reject_negative_values() -> None:
    with pytest.raises(ValidationError):
        PipelineMetrics(records_fetched=-1)
