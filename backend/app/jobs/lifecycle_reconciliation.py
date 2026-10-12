import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.absence_confirmation import AbsenceConfirmationService
from app.jobs.first_absence import FirstAbsenceDetectionService
from app.jobs.presence import PresenceRun, PresenceUnsafeReason
from app.jobs.presence_service import PresenceSetBuilder
from app.jobs.present_reconciliation import PresentJobReconciliationService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LifecycleReconciliationResult:
    performed: bool
    skipped_reason: PresenceUnsafeReason | None = None
    tentative_absences_reset: int = 0
    jobs_reappeared: int = 0
    first_absences_detected: int = 0
    jobs_confirmed_not_observed: int = 0


class LifecycleReconciliationService:
    """Compose lifecycle batches after record processing, before run finalization."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        present_reconciliation: PresentJobReconciliationService | None = None,
        absence_confirmation: AbsenceConfirmationService | None = None,
        first_absence_detection: FirstAbsenceDetectionService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._present = present_reconciliation or PresentJobReconciliationService(
            session_factory
        )
        self._confirmation = absence_confirmation or AbsenceConfirmationService(
            session_factory
        )
        self._first_absence = first_absence_detection or FirstAbsenceDetectionService(
            session_factory
        )

    async def reconcile_processed_run(
        self, processed_run: PresenceRun, *, session: AsyncSession | None = None
    ) -> LifecycleReconciliationResult:
        if session is not None:
            return await self._reconcile_processed_run(session, processed_run)
        async with self._session_factory.begin() as owned_session:
            return await self._reconcile_processed_run(owned_session, processed_run)

    async def _reconcile_processed_run(
        self, session: AsyncSession, processed_run: PresenceRun
    ) -> LifecycleReconciliationResult:
        stage = "presence_set"
        log_fields = {
            "pipeline_run_id": str(processed_run.pipeline_run_id),
            "source_connection_id": str(processed_run.source_connection_id),
        }
        try:
            presence = await PresenceSetBuilder(session).build_presence_set(
                processed_run.pipeline_run_id, processed_run=processed_run
            )
            if not presence.presence_reconciliation_safe:
                logger.info(
                    "lifecycle_reconciliation_skipped",
                    extra={**log_fields, "skipped_reason": presence.unsafe_reason},
                )
                return LifecycleReconciliationResult(
                    performed=False, skipped_reason=presence.unsafe_reason
                )

            stage = "present_reconciliation"
            present = await self._present.reconcile_present_jobs(
                processed_run.pipeline_run_id,
                processed_run=processed_run,
                session=session,
            )
            stage = "absence_confirmation"
            confirmed = await self._confirmation.confirm_absences(
                processed_run.pipeline_run_id,
                processed_run=processed_run,
                session=session,
            )
            # Confirmation must precede creation of this run's new first absences.
            stage = "first_absence_detection"
            first = await self._first_absence.detect_first_absences(
                processed_run.pipeline_run_id,
                processed_run=processed_run,
                session=session,
            )
        except Exception:
            logger.exception(
                "lifecycle_reconciliation_failed", extra={**log_fields, "stage": stage}
            )
            raise

        return LifecycleReconciliationResult(
            performed=True,
            tentative_absences_reset=present.tentative_absences_reset,
            jobs_reappeared=present.jobs_reappeared,
            first_absences_detected=first.first_absences_detected,
            jobs_confirmed_not_observed=confirmed.confirmed_not_observed,
        )
