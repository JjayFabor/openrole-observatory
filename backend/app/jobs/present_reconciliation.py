import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.lifecycle_errors import (
    PresenceDataInvariantError,
    PresenceReconciliationUnsafeError,
)
from app.jobs.lifecycle_repository import JobLifecycleRepository
from app.jobs.lifecycle_timing import validate_lifecycle_evidence_time
from app.jobs.models import (
    JobLifecycleEvent,
    JobLifecycleEventType,
    JobLifecycleStatus,
)
from app.jobs.presence import PresenceRun
from app.jobs.presence_service import PresenceSetBuilder

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PresentJobReconciliationResult:
    pipeline_run_id: UUID
    source_connection_id: UUID
    evaluated_present_jobs: int
    tentative_absences_reset: int
    jobs_reappeared: int
    quarantine_presence_only: int


class PresentJobReconciliationService:
    """Reset tentative absences and atomically record confirmed reappearances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def reconcile_present_jobs(
        self,
        pipeline_run_id: UUID,
        *,
        processed_run: PresenceRun | None = None,
        session: AsyncSession | None = None,
    ) -> PresentJobReconciliationResult:
        """Use the caller's transaction, or own one for standalone reconciliation."""
        if session is not None:
            return await self._reconcile_present_jobs(
                session, pipeline_run_id, processed_run
            )
        async with self._session_factory.begin() as owned_session:
            return await self._reconcile_present_jobs(
                owned_session, pipeline_run_id, processed_run
            )

    async def _reconcile_present_jobs(
        self,
        session: AsyncSession,
        pipeline_run_id: UUID,
        processed_run: PresenceRun | None,
    ) -> PresentJobReconciliationResult:
        presence = await PresenceSetBuilder(session).build_presence_set(
            pipeline_run_id, processed_run=processed_run
        )
        if not presence.presence_reconciliation_safe:
            assert presence.unsafe_reason is not None
            raise PresenceReconciliationUnsafeError(
                pipeline_run_id, presence.unsafe_reason.value
            )

        repository = JobLifecycleRepository(session)
        reconciliation_time = await repository.get_reconciliation_time(pipeline_run_id)
        if reconciliation_time is None:
            raise PresenceDataInvariantError(
                pipeline_run_id, "successful run has no snapshot observation time"
            )
        jobs = await repository.list_present_jobs_for_update(
            presence.source_connection_id, presence.present_external_job_ids
        )
        tentative_resets = 0
        quarantine_only = 0
        events: list[JobLifecycleEvent] = []
        for job in jobs:
            if job.lifecycle_status == JobLifecycleStatus.OBSERVED.value:
                if (
                    job.consecutive_absent_runs == 0
                    and job.absence_first_detected_at is None
                ):
                    continue
                validate_lifecycle_evidence_time(
                    job, pipeline_run_id, reconciliation_time
                )
                job.consecutive_absent_runs = 0
                job.absence_first_detected_at = None
                tentative_resets += 1
            elif job.lifecycle_status == JobLifecycleStatus.NOT_OBSERVED.value:
                if job.external_job_id not in presence.observed_external_job_ids:
                    quarantine_only += 1
                    continue
                validate_lifecycle_evidence_time(
                    job, pipeline_run_id, reconciliation_time
                )
                event = JobLifecycleEvent(
                    job_id=job.id,
                    pipeline_run_id=pipeline_run_id,
                    event_type=JobLifecycleEventType.REAPPEARED.value,
                    occurred_at=reconciliation_time,
                    previous_status=job.lifecycle_status,
                    new_status=JobLifecycleStatus.OBSERVED.value,
                    event_metadata={
                        "previous_consecutive_absent_runs": job.consecutive_absent_runs,
                        "previous_no_longer_observed_at": (
                            job.no_longer_observed_at.isoformat()
                            if job.no_longer_observed_at is not None
                            else None
                        ),
                    },
                )
                job.lifecycle_status = JobLifecycleStatus.OBSERVED.value
                job.consecutive_absent_runs = 0
                job.absence_first_detected_at = None
                job.reappeared_at = reconciliation_time
                events.append(event)
            else:
                raise PresenceDataInvariantError(
                    pipeline_run_id,
                    "present job has an unsupported lifecycle status",
                )

        await repository.add_lifecycle_events(events)
        result = PresentJobReconciliationResult(
            pipeline_run_id=pipeline_run_id,
            source_connection_id=presence.source_connection_id,
            evaluated_present_jobs=len(jobs),
            tentative_absences_reset=tentative_resets,
            jobs_reappeared=len(events),
            quarantine_presence_only=quarantine_only,
        )

        logger.info(
            "present_job_reconciliation_prepared",
            extra={
                "pipeline_run_id": str(result.pipeline_run_id),
                "source_connection_id": str(result.source_connection_id),
                "evaluated_present_jobs": result.evaluated_present_jobs,
                "tentative_absences_reset": result.tentative_absences_reset,
                "jobs_reappeared": result.jobs_reappeared,
                "quarantine_presence_only": result.quarantine_presence_only,
            },
        )
        return result
