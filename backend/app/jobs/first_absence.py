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
from app.jobs.models import JobLifecycleEvent, JobLifecycleEventType, JobLifecycleStatus
from app.jobs.presence import PresenceRun
from app.jobs.presence_service import PresenceSetBuilder

logger = logging.getLogger(__name__)


def find_missing_external_job_ids(
    observed_external_job_ids: frozenset[str], present_external_job_ids: frozenset[str]
) -> frozenset[str]:
    return observed_external_job_ids - present_external_job_ids


@dataclass(frozen=True, slots=True)
class FirstAbsenceDetectionResult:
    pipeline_run_id: UUID
    source_connection_id: UUID
    evaluated_jobs: int
    first_absences_detected: int
    skipped_already_absent: int


class FirstAbsenceDetectionService:
    """Record first absence signals from trusted runs in one atomic batch."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def detect_first_absences(
        self,
        pipeline_run_id: UUID,
        *,
        processed_run: PresenceRun | None = None,
        session: AsyncSession | None = None,
    ) -> FirstAbsenceDetectionResult:
        """Use the caller's transaction, or own one for standalone reconciliation."""
        if session is not None:
            return await self._detect_first_absences(
                session, pipeline_run_id, processed_run
            )
        async with self._session_factory.begin() as owned_session:
            return await self._detect_first_absences(
                owned_session, pipeline_run_id, processed_run
            )

    async def _detect_first_absences(
        self,
        session: AsyncSession,
        pipeline_run_id: UUID,
        processed_run: PresenceRun | None,
    ) -> FirstAbsenceDetectionResult:
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
        jobs = await repository.list_observed_jobs_for_update(
            presence.source_connection_id
        )
        missing_ids = find_missing_external_job_ids(
            frozenset(job.external_job_id for job in jobs),
            presence.present_external_job_ids,
        )
        skipped_already_absent = 0
        events: list[JobLifecycleEvent] = []
        for job in jobs:
            if job.external_job_id not in missing_ids:
                continue
            if job.consecutive_absent_runs > 0:
                skipped_already_absent += 1
                continue
            if job.absence_first_detected_at is not None:
                raise PresenceDataInvariantError(
                    pipeline_run_id,
                    "zero-absence job already has a first-absence timestamp",
                )
            validate_lifecycle_evidence_time(job, pipeline_run_id, reconciliation_time)
            job.consecutive_absent_runs = 1
            job.absence_first_detected_at = reconciliation_time
            events.append(
                JobLifecycleEvent(
                    job_id=job.id,
                    pipeline_run_id=pipeline_run_id,
                    event_type=JobLifecycleEventType.ABSENCE_DETECTED.value,
                    occurred_at=reconciliation_time,
                    previous_status=JobLifecycleStatus.OBSERVED.value,
                    new_status=JobLifecycleStatus.OBSERVED.value,
                    event_metadata={"consecutive_absent_runs": 1},
                )
            )

        await repository.add_lifecycle_events(events)
        result = FirstAbsenceDetectionResult(
            pipeline_run_id=pipeline_run_id,
            source_connection_id=presence.source_connection_id,
            evaluated_jobs=len(jobs),
            first_absences_detected=len(events),
            skipped_already_absent=skipped_already_absent,
        )

        logger.info(
            "first_absence_detection_prepared",
            extra={
                "pipeline_run_id": str(result.pipeline_run_id),
                "source_connection_id": str(result.source_connection_id),
                "evaluated_jobs": result.evaluated_jobs,
                "first_absences_detected": result.first_absences_detected,
                "skipped_already_absent": result.skipped_already_absent,
            },
        )
        return result
