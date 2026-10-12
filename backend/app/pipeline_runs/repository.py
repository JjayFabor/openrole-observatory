from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.sources.models import SourceConnection


class PipelineRunRepository:
    """Minimum persistence operations needed by the lifecycle service."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_source(
        self,
        source_connection_id: UUID,
    ) -> SourceConnection | None:
        return await self._session.get(SourceConnection, source_connection_id)

    async def get_source_for_update(
        self,
        source_connection_id: UUID,
    ) -> SourceConnection | None:
        return await self._session.scalar(
            select(SourceConnection)
            .where(SourceConnection.id == source_connection_id)
            .with_for_update()
        )

    async def create_pending(self, run: PipelineRun) -> PipelineRun:
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_run_for_update(self, pipeline_run_id: UUID) -> PipelineRun | None:
        return await self._session.scalar(
            select(PipelineRun)
            .where(PipelineRun.id == pipeline_run_id)
            .with_for_update()
        )

    async def get_run(self, pipeline_run_id: UUID) -> PipelineRun | None:
        return await self._session.get(PipelineRun, pipeline_run_id)

    async def list_runs(
        self,
        *,
        limit: int,
        offset: int,
        source_connection_id: UUID | None = None,
        status: PipelineRunStatus | None = None,
    ) -> list[PipelineRun]:
        statement = select(PipelineRun)
        if status is not None:
            statement = statement.where(PipelineRun.status == status)
        if source_connection_id is not None:
            statement = statement.where(
                PipelineRun.source_connection_id == source_connection_id
            )
        return list(
            (
                await self._session.scalars(
                    statement.order_by(
                        PipelineRun.started_at.desc(), PipelineRun.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
