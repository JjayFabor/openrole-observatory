import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
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


@dataclass(frozen=True, slots=True)
class AbsenceConfirmationResult:
    pipeline_run_id: UUID
    source_connection_id: UUID
    evaluated_jobs: int
    confirmed_not_observed: int
    skipped_present: int
    skipped_already_applied: int


class AbsenceConfirmationService:
    """Confirm a second safe absence with atomic state and event persistence."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._confirmation_threshold = (
            settings or get_settings()
        ).job_absence_confirmation_runs

    async def confirm_absences(
        self,
        pipeline_run_id: UUID,
        *,
        processed_run: PresenceRun | None = None,
        session: AsyncSession | None = None,
    ) -> AbsenceConfirmationResult:
        """Use the caller's transaction, or own one for standalone reconciliation."""
        if session is not None:
            return await self._confirm_absences(session, pipeline_run_id, processed_run)
        async with self._session_factory.begin() as owned_session:
            return await self._confirm_absences(
                owned_session, pipeline_run_id, processed_run
            )

    async def _confirm_absences(
        self,
        session: AsyncSession,
        pipeline_run_id: UUID,
        processed_run: PresenceRun | None,
    ) -> AbsenceConfirmationResult:
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
        jobs = await repository.list_absence_confirmation_jobs_for_update(
            presence.source_connection_id
        )
        counted_job_ids = await repository.get_jobs_with_absence_events_for_run(
            presence.source_connection_id, pipeline_run_id
        )
        skipped_present = 0
        skipped_already_applied = 0
        events: list[JobLifecycleEvent] = []
        for job in jobs:
            if job.external_job_id in presence.present_external_job_ids:
                skipped_present += 1
                continue
            if job.id in counted_job_ids:
                skipped_already_applied += 1
                continue
            if job.consecutive_absent_runs != self._confirmation_threshold - 1:
                raise PresenceDataInvariantError(
                    pipeline_run_id,
                    "observed job has an unsupported absence count for Phase 2",
                )
            if job.absence_first_detected_at is None:
                raise PresenceDataInvariantError(
                    pipeline_run_id,
                    "absence-count job has no first-absence timestamp",
                )
            validate_lifecycle_evidence_time(job, pipeline_run_id, reconciliation_time)
            if reconciliation_time <= job.absence_first_detected_at:
                raise PresenceDataInvariantError(
                    pipeline_run_id,
                    "confirmation observation must be later than first absence",
                )

            job.consecutive_absent_runs += 1
            job.lifecycle_status = JobLifecycleStatus.NOT_OBSERVED.value
            job.no_longer_observed_at = reconciliation_time
            events.append(
                JobLifecycleEvent(
                    job_id=job.id,
                    pipeline_run_id=pipeline_run_id,
                    event_type=JobLifecycleEventType.NOT_OBSERVED_CONFIRMED.value,
                    occurred_at=reconciliation_time,
                    previous_status=JobLifecycleStatus.OBSERVED.value,
                    new_status=JobLifecycleStatus.NOT_OBSERVED.value,
                    event_metadata={
                        "consecutive_absent_runs": job.consecutive_absent_runs,
                        "confirmation_threshold": self._confirmation_threshold,
                    },
                )
            )

        await repository.add_lifecycle_events(events)
        result = AbsenceConfirmationResult(
            pipeline_run_id=pipeline_run_id,
            source_connection_id=presence.source_connection_id,
            evaluated_jobs=len(jobs),
            confirmed_not_observed=len(events),
            skipped_present=skipped_present,
            skipped_already_applied=skipped_already_applied,
        )

        logger.info(
            "absence_confirmation_prepared",
            extra={
                "pipeline_run_id": str(result.pipeline_run_id),
                "source_connection_id": str(result.source_connection_id),
                "evaluated_jobs": result.evaluated_jobs,
                "confirmed_not_observed": result.confirmed_not_observed,
                "skipped_present": result.skipped_present,
                "skipped_already_applied": result.skipped_already_applied,
            },
        )
        return result
