from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.pipeline_runs.models import PipelineRunStatus
from app.pipeline_runs.repository import PipelineRunRepository
from app.pipeline_runs.schemas import PipelineRunRead


class PipelineRunQueryService:
    """Provide read-only pipeline-run views for administrative adapters."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get(self, pipeline_run_id: UUID) -> PipelineRunRead | None:
        async with self._session_factory() as session:
            run = await PipelineRunRepository(session).get_run(pipeline_run_id)
            return PipelineRunRead.model_validate(run) if run is not None else None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        source_connection_id: UUID | None = None,
        status: PipelineRunStatus | None = None,
    ) -> list[PipelineRunRead]:
        async with self._session_factory() as session:
            runs = await PipelineRunRepository(session).list_runs(
                limit=limit,
                offset=offset,
                source_connection_id=source_connection_id,
                status=status,
            )
            return [PipelineRunRead.model_validate(run) for run in runs]
