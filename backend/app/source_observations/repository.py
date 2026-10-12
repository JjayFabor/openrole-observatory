from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline_runs.models import PipelineRun
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.models import SourceConnection


@dataclass(frozen=True, slots=True)
class SourceProcessingContext:
    raw_snapshot: RawSnapshot
    pipeline_run: PipelineRun
    source_connection: SourceConnection
    has_observations: bool


class SourceObservationRepository:
    """Persistence operations needed by one source-record processing pass."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_processing_context(
        self,
        raw_snapshot_id: UUID,
        *,
        for_update: bool = False,
    ) -> SourceProcessingContext | None:
        statement = (
            select(RawSnapshot, PipelineRun, SourceConnection)
            .join(
                PipelineRun,
                PipelineRun.id == RawSnapshot.pipeline_run_id,
            )
            .join(
                SourceConnection,
                SourceConnection.id == PipelineRun.source_connection_id,
            )
            .where(RawSnapshot.id == raw_snapshot_id)
        )
        if for_update:
            statement = statement.with_for_update(
                of=(RawSnapshot, PipelineRun, SourceConnection)
            )

        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None

        raw_snapshot, pipeline_run, source_connection = row
        has_observations = await self._session.scalar(
            select(exists().where(SourceObservation.raw_snapshot_id == raw_snapshot_id))
        )
        return SourceProcessingContext(
            raw_snapshot=raw_snapshot,
            pipeline_run=pipeline_run,
            source_connection=source_connection,
            has_observations=has_observations is True,
        )

    async def persist_processing_result(
        self,
        *,
        raw_snapshot: RawSnapshot,
        record_count: int,
        observations: list[SourceObservation],
    ) -> None:
        raw_snapshot.record_count = record_count
        self._session.add_all(observations)
        await self._session.flush()
