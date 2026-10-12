from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.presence import PresenceRecord, PresenceRun
from app.pipeline_runs.models import PipelineRun
from app.quarantine.models import QuarantineRecord
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation


class PresenceRepository:
    """Read only the fields needed to validate persisted source-run evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_run(self, pipeline_run_id: UUID) -> PresenceRun | None:
        row = (
            await self._session.execute(
                select(
                    PipelineRun.id,
                    PipelineRun.source_connection_id,
                    PipelineRun.status,
                    PipelineRun.records_fetched,
                    PipelineRun.records_valid,
                    PipelineRun.records_quarantined,
                ).where(PipelineRun.id == pipeline_run_id)
            )
        ).one_or_none()
        return PresenceRun(*row) if row is not None else None

    async def list_observations(self, pipeline_run_id: UUID) -> list[PresenceRecord]:
        rows = await self._session.execute(
            select(
                SourceObservation.source_connection_id,
                SourceObservation.raw_snapshot_id,
                RawSnapshot.pipeline_run_id,
                SourceObservation.raw_record_locator,
                SourceObservation.external_job_id,
            )
            .join(RawSnapshot, RawSnapshot.id == SourceObservation.raw_snapshot_id)
            .where(SourceObservation.pipeline_run_id == pipeline_run_id)
        )
        return [PresenceRecord(*row) for row in rows]

    async def get_snapshot_record_count(self, pipeline_run_id: UUID) -> int | None:
        return await self._session.scalar(
            select(RawSnapshot.record_count).where(
                RawSnapshot.pipeline_run_id == pipeline_run_id
            )
        )

    async def list_quarantines(self, pipeline_run_id: UUID) -> list[PresenceRecord]:
        rows = await self._session.execute(
            select(
                QuarantineRecord.source_connection_id,
                QuarantineRecord.raw_snapshot_id,
                RawSnapshot.pipeline_run_id,
                QuarantineRecord.raw_record_locator,
                QuarantineRecord.external_job_id,
            )
            .join(RawSnapshot, RawSnapshot.id == QuarantineRecord.raw_snapshot_id)
            .where(QuarantineRecord.pipeline_run_id == pipeline_run_id)
        )
        return [PresenceRecord(*row) for row in rows]
