import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.lifecycle_errors import (
    PresenceDataInvariantError,
    PresenceReconciliationNotAllowedError,
)
from app.jobs.presence import PresenceRun, PresenceSetResult, build_presence_set
from app.jobs.presence_repository import PresenceRepository
from app.pipeline_runs.errors import PipelineRunNotFoundError
from app.pipeline_runs.models import PipelineRunStatus

logger = logging.getLogger(__name__)


class PresenceSetBuilder:
    """Build evidence in the caller's session without owning or committing writes."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = PresenceRepository(session)

    async def build_presence_set(
        self, pipeline_run_id: UUID, *, processed_run: PresenceRun | None = None
    ) -> PresenceSetResult:
        run = await self._repository.get_run(pipeline_run_id)
        if run is None:
            raise PipelineRunNotFoundError(pipeline_run_id)
        if processed_run is not None:
            if run.status != PipelineRunStatus.RUNNING.value:
                raise PresenceReconciliationNotAllowedError(
                    pipeline_run_id,
                    run.status,
                    required_status="running with a successful record-stage handoff",
                )
            if (
                processed_run.pipeline_run_id != run.pipeline_run_id
                or processed_run.source_connection_id != run.source_connection_id
            ):
                raise PresenceDataInvariantError(
                    pipeline_run_id, "processed-run handoff does not match stored run"
                )
            # Only the internal record-stage handoff supplies pre-finalization metrics.
            # Its expected successful outcome is validated against durable rows below.
            run = processed_run
        elif run.status not in {
            PipelineRunStatus.COMPLETED.value,
            PipelineRunStatus.COMPLETED_WITH_ERRORS.value,
        }:
            raise PresenceReconciliationNotAllowedError(pipeline_run_id, run.status)
        snapshot_count = await self._repository.get_snapshot_record_count(
            pipeline_run_id
        )
        if snapshot_count is None:
            raise PresenceDataInvariantError(
                pipeline_run_id, "successful run has no processed snapshot record count"
            )
        if snapshot_count != run.records_fetched:
            raise PresenceDataInvariantError(
                pipeline_run_id, "snapshot record count does not match records_fetched"
            )
        observations = await self._repository.list_observations(pipeline_run_id)
        quarantines = await self._repository.list_quarantines(pipeline_run_id)
        result = build_presence_set(run, observations, quarantines)
        logger.info(
            "presence_set_built",
            extra={
                "pipeline_run_id": str(result.pipeline_run_id),
                "source_connection_id": str(result.source_connection_id),
                "present_count": len(result.present_external_job_ids),
                "quarantined_count": result.quarantined_record_count,
                "unidentified_quarantine_count": result.unidentified_quarantine_count,
                "safe": result.presence_reconciliation_safe,
            },
        )
        return result
