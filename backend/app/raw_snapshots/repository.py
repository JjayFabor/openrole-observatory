from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline_runs.models import PipelineRun
from app.raw_snapshots.models import RawSnapshot
from app.sources.models import SourceConnection


@dataclass(frozen=True, slots=True)
class RawAcquisitionContext:
    pipeline_run_id: UUID
    source_connection_id: UUID
    pipeline_run_status: str
    source_is_active: bool
    provider: str
    external_account_key: str
    raw_snapshot_id: UUID | None


class RawSnapshotRepository:
    """Persistence needed to validate and record one raw acquisition."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_acquisition_context(
        self,
        pipeline_run_id: UUID,
        *,
        for_update: bool = False,
    ) -> RawAcquisitionContext | None:
        statement = (
            select(PipelineRun, SourceConnection)
            .join(
                SourceConnection,
                SourceConnection.id == PipelineRun.source_connection_id,
            )
            .where(PipelineRun.id == pipeline_run_id)
        )
        if for_update:
            statement = statement.with_for_update(of=(PipelineRun, SourceConnection))

        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None

        pipeline_run, source = row
        raw_snapshot_id = await self._session.scalar(
            select(RawSnapshot.id).where(RawSnapshot.pipeline_run_id == pipeline_run_id)
        )
        return RawAcquisitionContext(
            pipeline_run_id=pipeline_run.id,
            source_connection_id=source.id,
            pipeline_run_status=pipeline_run.status,
            source_is_active=source.is_active,
            provider=source.provider,
            external_account_key=source.external_account_key,
            raw_snapshot_id=raw_snapshot_id,
        )

    async def create(self, raw_snapshot: RawSnapshot) -> RawSnapshot:
        self._session.add(raw_snapshot)
        await self._session.flush()
        return raw_snapshot
