import logging
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.errors import (
    RawSnapshotPersistenceError,
    SnapshotRecordProcessingFailedError,
    SourceSyncFailedError,
)
from app.ingestion.locking import SourceRunLock
from app.ingestion.orchestration import (
    DATABASE_WRITE_FAILED,
    PIPELINE_INTERNAL_ERROR,
    RAW_STORAGE_FAILED,
    SOURCE_RESPONSE_INVALID,
    SnapshotIngestionOrchestrator,
)
from app.ingestion.raw_acquisition import RawSnapshotAcquisitionService
from app.jobs.lifecycle_reconciliation import (
    LifecycleReconciliationResult,
    LifecycleReconciliationService,
)
from app.jobs.presence import PresenceRun
from app.pipeline_runs.errors import (
    PipelineRunAlreadyFinalizedError,
    PipelineRunNotFoundError,
    SourceConnectionInactiveError,
    SourceConnectionNotFoundError,
    SourceSyncAlreadyRunningError,
)
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.pipeline_runs.repository import PipelineRunRepository
from app.pipeline_runs.schemas import PipelineMetrics
from app.pipeline_runs.service import PipelineRunService
from app.sources.greenhouse.errors import (
    GreenhouseError,
    GreenhouseTimeoutError,
)
from app.storage.errors import StorageError

logger = logging.getLogger(__name__)

SOURCE_REQUEST_FAILED = "SOURCE_REQUEST_FAILED"
SOURCE_REQUEST_TIMEOUT = "SOURCE_REQUEST_TIMEOUT"


@dataclass(frozen=True, slots=True)
class SourceSyncResult:
    pipeline_run_id: UUID
    source_connection_id: UUID
    status: PipelineRunStatus
    records_fetched: int
    records_valid: int
    records_quarantined: int
    jobs_new: int
    jobs_changed: int
    jobs_unchanged: int
    started_at: datetime
    completed_at: datetime | None
    lifecycle: LifecycleReconciliationResult | None = None

    @classmethod
    def from_pipeline_run(
        cls, run: PipelineRun, lifecycle: LifecycleReconciliationResult | None = None
    ) -> "SourceSyncResult":
        return cls(
            pipeline_run_id=run.id,
            source_connection_id=run.source_connection_id,
            status=PipelineRunStatus(run.status),
            records_fetched=run.records_fetched,
            records_valid=run.records_valid,
            records_quarantined=run.records_quarantined,
            jobs_new=run.jobs_new,
            jobs_changed=run.jobs_changed,
            jobs_unchanged=run.jobs_unchanged,
            started_at=run.started_at,
            completed_at=run.completed_at,
            lifecycle=lifecycle,
        )


class SourceSyncService:
    """Coordinate one complete source synchronization under a per-source lock."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        source_run_lock: SourceRunLock,
        pipeline_run_service: PipelineRunService,
        raw_acquisition_service: RawSnapshotAcquisitionService,
        snapshot_orchestrator: SnapshotIngestionOrchestrator,
        lifecycle_reconciliation: LifecycleReconciliationService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._source_run_lock = source_run_lock
        self._pipeline_runs = pipeline_run_service
        self._raw_acquisition = raw_acquisition_service
        self._snapshot_orchestrator = snapshot_orchestrator
        self._lifecycle = lifecycle_reconciliation or LifecycleReconciliationService(
            session_factory
        )

    async def sync_source(self, source_connection_id: UUID) -> SourceSyncResult:
        await self._validate_source(source_connection_id)
        sync_started = time.monotonic()

        try:
            async with self._source_run_lock.hold(source_connection_id):
                run = await self._pipeline_runs.start(source_connection_id)
                log_fields = {
                    "source_connection_id": str(source_connection_id),
                    "pipeline_run_id": str(run.id),
                }
                logger.info("source_sync_started", extra=log_fields)

                metrics = PipelineMetrics()
                stage = "raw_acquisition"
                try:
                    raw_snapshot = await self._raw_acquisition.acquire(
                        pipeline_run_id=run.id,
                        source_connection_id=source_connection_id,
                    )
                    stage = "record_processing"
                    processed = await self._snapshot_orchestrator.process_records(
                        pipeline_run_id=run.id,
                        raw_snapshot_id=raw_snapshot.id,
                    )
                    metrics = processed.metrics
                    if processed.pipeline_run_id != run.id:
                        raise RuntimeError(
                            "record-stage handoff belongs to another run"
                        )
                    stage = "lifecycle_reconciliation"
                    async with self._session_factory.begin() as session:
                        lifecycle = await self._lifecycle.reconcile_processed_run(
                            PresenceRun(
                                pipeline_run_id=run.id,
                                source_connection_id=source_connection_id,
                                status=processed.status.value,
                                records_fetched=processed.records_fetched,
                                records_valid=processed.records_valid,
                                records_quarantined=processed.records_quarantined,
                            ),
                            session=session,
                        )
                        stage = "finalization"
                        if processed.status is PipelineRunStatus.COMPLETED_WITH_ERRORS:
                            final_run = await self._pipeline_runs.complete_with_errors(
                                run.id, metrics, session=session
                            )
                        else:
                            final_run = await self._pipeline_runs.complete(
                                run.id, metrics, session=session
                            )
                        result = SourceSyncResult.from_pipeline_run(
                            final_run, lifecycle
                        )
                        if result.status not in {
                            PipelineRunStatus.COMPLETED,
                            PipelineRunStatus.COMPLETED_WITH_ERRORS,
                        }:
                            raise RuntimeError(
                                "snapshot processing returned without a successful "
                                "terminal pipeline run"
                            )
                        if result.completed_at is None:
                            raise RuntimeError(
                                "successful pipeline run has no completion timestamp"
                            )
                except Exception as error:
                    sync_error = await self._build_sync_failure(
                        source_connection_id=source_connection_id,
                        pipeline_run_id=run.id,
                        error=error,
                        metrics=(
                            error.metrics
                            if isinstance(error, SnapshotRecordProcessingFailedError)
                            else metrics
                        ),
                    )
                    logger.exception(
                        "source_sync_failed",
                        extra={
                            **log_fields,
                            "error_code": sync_error.code,
                            "stage": stage,
                            "duration_ms": _duration_ms(sync_started),
                        },
                    )
                    raise sync_error from error

                event = (
                    "source_sync_completed_with_errors"
                    if result.status is PipelineRunStatus.COMPLETED_WITH_ERRORS
                    else "source_sync_completed"
                )
                logger.info(
                    event,
                    extra={
                        **log_fields,
                        "status": result.status.value,
                        "duration_ms": _duration_ms(sync_started),
                        "records_fetched": result.records_fetched,
                        "records_valid": result.records_valid,
                        "records_quarantined": result.records_quarantined,
                        "jobs_new": result.jobs_new,
                        "jobs_changed": result.jobs_changed,
                        "jobs_unchanged": result.jobs_unchanged,
                        "lifecycle_performed": lifecycle.performed,
                        "lifecycle_skipped_reason": lifecycle.skipped_reason,
                        "tentative_absences_reset": lifecycle.tentative_absences_reset,
                        "jobs_reappeared": lifecycle.jobs_reappeared,
                        "first_absences_detected": lifecycle.first_absences_detected,
                        "jobs_confirmed_not_observed": lifecycle.jobs_confirmed_not_observed,
                    },
                )
                return result
        except SourceSyncAlreadyRunningError:
            logger.info(
                "source_sync_lock_conflict",
                extra={"source_connection_id": str(source_connection_id)},
            )
            raise

    async def _validate_source(self, source_connection_id: UUID) -> None:
        async with self._session_factory() as session:
            source = await PipelineRunRepository(session).get_source(
                source_connection_id
            )
        if source is None:
            raise SourceConnectionNotFoundError(source_connection_id)
        if not source.is_active:
            raise SourceConnectionInactiveError(source_connection_id)

    async def _require_run(self, pipeline_run_id: UUID) -> PipelineRun:
        async with self._session_factory() as session:
            run = await PipelineRunRepository(session).get_run(pipeline_run_id)
        if run is None:
            raise PipelineRunNotFoundError(pipeline_run_id)
        return run

    async def _build_sync_failure(
        self,
        *,
        source_connection_id: UUID,
        pipeline_run_id: UUID,
        error: Exception,
        metrics: PipelineMetrics,
    ) -> SourceSyncFailedError:
        fallback_code, fallback_summary = _classify_sync_failure(error)

        try:
            run = await self._require_run(pipeline_run_id)
            if run.status == PipelineRunStatus.RUNNING.value:
                try:
                    run = await self._pipeline_runs.fail(
                        pipeline_run_id,
                        error_code=fallback_code,
                        error_summary=fallback_summary,
                        metrics=metrics,
                    )
                except PipelineRunAlreadyFinalizedError:
                    run = await self._require_run(pipeline_run_id)

            if run.status == PipelineRunStatus.FAILED.value:
                error_code = run.error_code or fallback_code
                error_summary = run.error_summary or fallback_summary
            else:
                error_code = fallback_code
                error_summary = fallback_summary
        except Exception:
            logger.exception(
                "source_sync_failure_finalization_failed",
                extra={
                    "source_connection_id": str(source_connection_id),
                    "pipeline_run_id": str(pipeline_run_id),
                },
            )
            error_code = fallback_code
            error_summary = fallback_summary

        return SourceSyncFailedError(
            source_connection_id=source_connection_id,
            pipeline_run_id=pipeline_run_id,
            error_code=error_code,
            safe_message=error_summary,
        )


def _classify_sync_failure(error: Exception) -> tuple[str, str]:
    if isinstance(error, SnapshotRecordProcessingFailedError):
        return error.code, error.safe_message
    if isinstance(error, GreenhouseTimeoutError):
        return SOURCE_REQUEST_TIMEOUT, "The source request timed out."
    if isinstance(error, GreenhouseError):
        return SOURCE_REQUEST_FAILED, "The source request could not be completed."
    if isinstance(error, StorageError):
        return RAW_STORAGE_FAILED, "Raw source storage could not be completed."
    if isinstance(error, (RawSnapshotPersistenceError, SQLAlchemyError)):
        return DATABASE_WRITE_FAILED, "Database processing could not be completed."
    if isinstance(error, SourceSyncFailedError):
        return error.code, error.safe_message
    if getattr(error, "code", None) == SOURCE_RESPONSE_INVALID:
        return SOURCE_RESPONSE_INVALID, "The source response could not be processed."
    return PIPELINE_INTERNAL_ERROR, "Source synchronization could not be completed."


def _duration_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
