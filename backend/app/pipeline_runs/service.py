import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.pipeline_runs.errors import (
    PipelineRunAlreadyFinalizedError,
    PipelineRunInvalidTransitionError,
    PipelineRunNotFoundError,
    SourceConnectionInactiveError,
    SourceConnectionNotFoundError,
)
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.pipeline_runs.repository import PipelineRunRepository
from app.pipeline_runs.schemas import PipelineMetrics

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
TERMINAL_STATUSES = frozenset(
    {
        PipelineRunStatus.COMPLETED.value,
        PipelineRunStatus.COMPLETED_WITH_ERRORS.value,
        PipelineRunStatus.FAILED.value,
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PipelineRunService:
    """Manage source-independent pipeline-run lifecycle transitions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def start(self, source_connection_id: UUID) -> PipelineRun:
        pending = await self._create_pending(source_connection_id)
        return await self.mark_running(pending.id)

    async def mark_running(self, pipeline_run_id: UUID) -> PipelineRun:
        async with self._session_factory.begin() as session:
            repository = PipelineRunRepository(session)
            run = await self._get_run(repository, pipeline_run_id)
            self._validate_transition(run, PipelineRunStatus.RUNNING)

            source = await repository.get_source_for_update(run.source_connection_id)
            if source is None:
                raise SourceConnectionNotFoundError(run.source_connection_id)
            if not source.is_active:
                raise SourceConnectionInactiveError(source.id)

            started_at = self._now()
            run.status = PipelineRunStatus.RUNNING.value
            run.started_at = started_at
            source.last_attempted_sync_at = started_at
            await session.flush()

        logger.info(
            "pipeline_run_started",
            extra={
                "pipeline_run_id": str(run.id),
                "source_connection_id": str(run.source_connection_id),
                "status": run.status,
            },
        )
        return run

    async def complete(
        self,
        pipeline_run_id: UUID,
        metrics: PipelineMetrics,
        *,
        session: AsyncSession | None = None,
    ) -> PipelineRun:
        return await self._finalize(
            pipeline_run_id,
            target=PipelineRunStatus.COMPLETED,
            metrics=metrics,
            session=session,
        )

    async def complete_with_errors(
        self,
        pipeline_run_id: UUID,
        metrics: PipelineMetrics,
        *,
        session: AsyncSession | None = None,
    ) -> PipelineRun:
        return await self._finalize(
            pipeline_run_id,
            target=PipelineRunStatus.COMPLETED_WITH_ERRORS,
            metrics=metrics,
            session=session,
        )

    async def fail(
        self,
        pipeline_run_id: UUID,
        *,
        error_code: str,
        error_summary: str,
        metrics: PipelineMetrics | None = None,
    ) -> PipelineRun:
        normalized_code = error_code.strip()
        normalized_summary = error_summary.strip()
        if not normalized_code:
            raise ValueError("error_code must not be blank")
        if not normalized_summary:
            raise ValueError("error_summary must not be blank")

        return await self._finalize(
            pipeline_run_id,
            target=PipelineRunStatus.FAILED,
            metrics=metrics or PipelineMetrics(),
            error_code=normalized_code,
            error_summary=normalized_summary,
        )

    async def _create_pending(self, source_connection_id: UUID) -> PipelineRun:
        async with self._session_factory.begin() as session:
            repository = PipelineRunRepository(session)
            source = await repository.get_source_for_update(source_connection_id)
            if source is None:
                raise SourceConnectionNotFoundError(source_connection_id)
            if not source.is_active:
                raise SourceConnectionInactiveError(source_connection_id)

            run = PipelineRun(
                source_connection_id=source_connection_id,
                status=PipelineRunStatus.PENDING.value,
                started_at=self._now(),
            )
            await repository.create_pending(run)

        return run

    async def _finalize(
        self,
        pipeline_run_id: UUID,
        *,
        target: PipelineRunStatus,
        metrics: PipelineMetrics,
        error_code: str | None = None,
        error_summary: str | None = None,
        session: AsyncSession | None = None,
    ) -> PipelineRun:
        if session is not None:
            return await self._finalize_in_session(
                session, pipeline_run_id, target, metrics, error_code, error_summary
            )
        async with self._session_factory.begin() as owned_session:
            return await self._finalize_in_session(
                owned_session,
                pipeline_run_id,
                target,
                metrics,
                error_code,
                error_summary,
            )

    async def _finalize_in_session(
        self,
        session: AsyncSession,
        pipeline_run_id: UUID,
        target: PipelineRunStatus,
        metrics: PipelineMetrics,
        error_code: str | None,
        error_summary: str | None,
    ) -> PipelineRun:
        repository = PipelineRunRepository(session)
        run = await self._get_run(repository, pipeline_run_id)
        self._validate_transition(run, target)
        completed_at = self._now()

        self._assign_metrics(run, metrics)
        run.status = target.value
        run.completed_at = completed_at
        run.error_code = error_code
        run.error_summary = error_summary

        if target in {
            PipelineRunStatus.COMPLETED,
            PipelineRunStatus.COMPLETED_WITH_ERRORS,
        }:
            source = await repository.get_source_for_update(run.source_connection_id)
            if source is None:
                raise SourceConnectionNotFoundError(run.source_connection_id)
            source.last_successful_sync_at = completed_at

        await session.flush()

        logger.info(
            "pipeline_run_finalization_prepared",
            extra={
                "pipeline_run_id": str(run.id),
                "source_connection_id": str(run.source_connection_id),
                "status": run.status,
            },
        )
        return run

    async def _get_run(
        self,
        repository: PipelineRunRepository,
        pipeline_run_id: UUID,
    ) -> PipelineRun:
        run = await repository.get_run_for_update(pipeline_run_id)
        if run is None:
            raise PipelineRunNotFoundError(pipeline_run_id)
        return run

    @staticmethod
    def _validate_transition(run: PipelineRun, target: PipelineRunStatus) -> None:
        if run.status in TERMINAL_STATUSES:
            raise PipelineRunAlreadyFinalizedError(
                run.id,
                run.status,
                target.value,
            )

        valid = (
            run.status == PipelineRunStatus.PENDING.value
            and target is PipelineRunStatus.RUNNING
        ) or (
            run.status == PipelineRunStatus.RUNNING.value
            and target
            in {
                PipelineRunStatus.COMPLETED,
                PipelineRunStatus.COMPLETED_WITH_ERRORS,
                PipelineRunStatus.FAILED,
            }
        )
        if not valid:
            raise PipelineRunInvalidTransitionError(
                run.id,
                run.status,
                target.value,
            )

    @staticmethod
    def _assign_metrics(run: PipelineRun, metrics: PipelineMetrics) -> None:
        run.records_fetched = metrics.records_fetched
        run.records_valid = metrics.records_valid
        run.records_quarantined = metrics.records_quarantined
        run.jobs_new = metrics.jobs_new
        run.jobs_changed = metrics.jobs_changed
        run.jobs_unchanged = metrics.jobs_unchanged

    def _now(self) -> datetime:
        timestamp = self._clock()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return timestamp.astimezone(UTC)
