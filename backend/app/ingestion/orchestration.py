import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.errors import (
    PipelineMetricsInvariantError,
    PipelineRunNotRunningError,
    RawSnapshotIntegrityError,
    RawSnapshotNotFoundError,
    RawSnapshotPipelineMismatchError,
    SnapshotRecordProcessingFailedError,
)
from app.ingestion.source_processing import (
    InvalidProcessedSourceRecord,
    ProcessedSourceRecord,
    SourceRecordProcessingService,
)
from app.jobs.errors import (
    ChangedJobDatabaseError,
    ChangedJobRequiresVersioningError,
    ExistingJobRequiresComparisonError,
    HistoricalJobContentAlreadyExistsError,
    NewJobDatabaseError,
    SourceRecordHashingError,
    SourceRecordNormalizationError,
    StaleJobObservationError,
    UnchangedJobDatabaseError,
)
from app.jobs.hashing import compute_canonical_job_hash
from app.jobs.service import (
    ApplyChangedObservationCommand,
    ApplyUnchangedObservationCommand,
    CanonicalHasher,
    CanonicalMapper,
    ChangedJobPersistenceService,
    NewJobPersistenceService,
    PersistNewJobCommand,
    UnchangedJobPersistenceService,
)
from app.pipeline_runs.errors import (
    PipelineRunAlreadyFinalizedError,
    SourceConnectionInactiveError,
)
from app.pipeline_runs.models import PipelineRunStatus
from app.pipeline_runs.schemas import PipelineMetrics
from app.pipeline_runs.service import TERMINAL_STATUSES, PipelineRunService
from app.quarantine.models import QuarantineRecord
from app.quarantine.repository import QuarantineRepository
from app.source_observations.repository import (
    SourceObservationRepository,
    SourceProcessingContext,
)
from app.sources.greenhouse.errors import GreenhouseResponseShapeError
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.storage.base import ObjectStorage
from app.storage.errors import StorageError

logger = logging.getLogger(__name__)

SOURCE_RESPONSE_INVALID = "SOURCE_RESPONSE_INVALID"
RAW_STORAGE_FAILED = "RAW_STORAGE_FAILED"
DATABASE_WRITE_FAILED = "DATABASE_WRITE_FAILED"
PIPELINE_INTERNAL_ERROR = "PIPELINE_INTERNAL_ERROR"


class JobProcessingOutcome(StrEnum):
    NEW = "new"
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class SnapshotIngestionResult:
    pipeline_run_id: UUID
    status: PipelineRunStatus
    records_fetched: int
    records_valid: int
    records_quarantined: int
    jobs_new: int
    jobs_changed: int
    jobs_unchanged: int

    @property
    def metrics(self) -> PipelineMetrics:
        return PipelineMetrics(
            records_fetched=self.records_fetched,
            records_valid=self.records_valid,
            records_quarantined=self.records_quarantined,
            jobs_new=self.jobs_new,
            jobs_changed=self.jobs_changed,
            jobs_unchanged=self.jobs_unchanged,
        )


@dataclass(slots=True)
class _MetricsAccumulator:
    records_fetched: int = 0
    records_valid: int = 0
    records_quarantined: int = 0
    jobs_new: int = 0
    jobs_changed: int = 0
    jobs_unchanged: int = 0

    def record_outcome(self, outcome: JobProcessingOutcome) -> None:
        if outcome is JobProcessingOutcome.QUARANTINED:
            self.records_quarantined += 1
            return

        self.records_valid += 1
        if outcome is JobProcessingOutcome.NEW:
            self.jobs_new += 1
        elif outcome is JobProcessingOutcome.CHANGED:
            self.jobs_changed += 1
        else:
            self.jobs_unchanged += 1

    def to_pipeline_metrics(self) -> PipelineMetrics:
        return PipelineMetrics(
            records_fetched=self.records_fetched,
            records_valid=self.records_valid,
            records_quarantined=self.records_quarantined,
            jobs_new=self.jobs_new,
            jobs_changed=self.jobs_changed,
            jobs_unchanged=self.jobs_unchanged,
        )


def validate_pipeline_metrics(metrics: PipelineMetrics) -> None:
    classified_records = metrics.records_valid + metrics.records_quarantined
    if metrics.records_fetched != classified_records:
        raise PipelineMetricsInvariantError(
            "records_fetched must equal records_valid plus records_quarantined"
        )

    successful_outcomes = (
        metrics.jobs_new + metrics.jobs_changed + metrics.jobs_unchanged
    )
    if metrics.records_valid != successful_outcomes:
        raise PipelineMetricsInvariantError(
            "records_valid must equal jobs_new plus jobs_changed plus jobs_unchanged"
        )


class SnapshotIngestionOrchestrator:
    """Process stored records; preserve a standalone finalizing entry point."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        object_storage: ObjectStorage,
        mapper: CanonicalMapper = map_greenhouse_job,
        hasher: CanonicalHasher = compute_canonical_job_hash,
        pipeline_run_service: PipelineRunService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._source_processing = SourceRecordProcessingService(
            session_factory,
            object_storage=object_storage,
        )
        self._new_jobs = NewJobPersistenceService(
            session_factory,
            mapper=mapper,
            hasher=hasher,
        )
        self._unchanged_jobs = UnchangedJobPersistenceService(
            session_factory,
            mapper=mapper,
            hasher=hasher,
        )
        self._changed_jobs = ChangedJobPersistenceService(
            session_factory,
            mapper=mapper,
            hasher=hasher,
        )
        self._pipeline_runs = pipeline_run_service or PipelineRunService(
            session_factory
        )

    async def process_snapshot(
        self,
        *,
        pipeline_run_id: UUID,
        raw_snapshot_id: UUID,
    ) -> SnapshotIngestionResult:
        """Compatibility entry point for standalone snapshot ingestion."""
        metrics = _MetricsAccumulator()
        try:
            result = await self._process_records(
                pipeline_run_id=pipeline_run_id,
                raw_snapshot_id=raw_snapshot_id,
                metrics=metrics,
            )
            if result.status is PipelineRunStatus.COMPLETED_WITH_ERRORS:
                await self._pipeline_runs.complete_with_errors(
                    pipeline_run_id, result.metrics
                )
            else:
                await self._pipeline_runs.complete(pipeline_run_id, result.metrics)
        except Exception as error:
            if not isinstance(error, PipelineRunAlreadyFinalizedError):
                await self._try_finalize_failure(
                    pipeline_run_id, error, metrics.to_pipeline_metrics()
                )
            raise
        return result

    async def process_records(
        self,
        *,
        pipeline_run_id: UUID,
        raw_snapshot_id: UUID,
    ) -> SnapshotIngestionResult:
        """Return a successful record-stage handoff without terminal run writes."""
        metrics = _MetricsAccumulator()
        try:
            return await self._process_records(
                pipeline_run_id=pipeline_run_id,
                raw_snapshot_id=raw_snapshot_id,
                metrics=metrics,
            )
        except Exception as error:
            code, summary = _classify_pipeline_failure(error)
            raise SnapshotRecordProcessingFailedError(
                metrics=metrics.to_pipeline_metrics(),
                error_code=code,
                safe_message=summary,
            ) from error

    async def _process_records(
        self,
        *,
        pipeline_run_id: UUID,
        raw_snapshot_id: UUID,
        metrics: _MetricsAccumulator,
    ) -> SnapshotIngestionResult:
        log_fields = {
            "pipeline_run_id": str(pipeline_run_id),
            "raw_snapshot_id": str(raw_snapshot_id),
        }
        logger.info("snapshot_ingestion_started", extra=log_fields)

        try:
            context = await self._load_and_validate_context(
                pipeline_run_id=pipeline_run_id,
                raw_snapshot_id=raw_snapshot_id,
            )
            source_result = await self._source_processing.process_raw_snapshot(
                pipeline_run_id=pipeline_run_id,
                raw_snapshot_id=raw_snapshot_id,
            )
            metrics.records_fetched = source_result.records_fetched
            logger.info(
                "source_records_validated",
                extra={
                    **log_fields,
                    "records_fetched": source_result.records_fetched,
                    "provider_valid_records": len(source_result.valid_records),
                    "provider_invalid_records": len(source_result.invalid_records),
                },
            )

            for invalid_record in source_result.invalid_records:
                await self._quarantine_invalid_record(context, invalid_record)
                metrics.record_outcome(JobProcessingOutcome.QUARANTINED)

            for processed_record in source_result.valid_records:
                try:
                    outcome = await self._route_record(processed_record)
                except (
                    SourceRecordNormalizationError,
                    SourceRecordHashingError,
                    StaleJobObservationError,
                    HistoricalJobContentAlreadyExistsError,
                ) as error:
                    await self._quarantine_record_error(
                        context,
                        processed_record,
                        error,
                    )
                    outcome = JobProcessingOutcome.QUARANTINED

                metrics.record_outcome(outcome)
                if outcome is not JobProcessingOutcome.QUARANTINED:
                    logger.debug(
                        "record_processed",
                        extra={
                            **log_fields,
                            "raw_record_locator": processed_record.raw_record_locator,
                            "external_job_id": str(processed_record.source_record.id),
                            "outcome": outcome.value,
                        },
                    )

            persisted_metrics = metrics.to_pipeline_metrics()
            validate_pipeline_metrics(persisted_metrics)
            status = (
                PipelineRunStatus.COMPLETED_WITH_ERRORS
                if persisted_metrics.records_quarantined
                else PipelineRunStatus.COMPLETED
            )
        except Exception as error:
            logger.exception(
                "snapshot_ingestion_failed",
                extra={**log_fields, "error_type": type(error).__name__},
            )
            raise

        logger.info(
            "snapshot_records_processed",
            extra={
                **log_fields,
                "status": status.value,
                **persisted_metrics.model_dump(),
            },
        )
        return SnapshotIngestionResult(
            pipeline_run_id=pipeline_run_id,
            status=status,
            **persisted_metrics.model_dump(),
        )

    async def _load_and_validate_context(
        self,
        *,
        pipeline_run_id: UUID,
        raw_snapshot_id: UUID,
    ) -> SourceProcessingContext:
        async with self._session_factory() as session:
            context = await SourceObservationRepository(session).get_processing_context(
                raw_snapshot_id
            )

        if context is None:
            raise RawSnapshotNotFoundError(raw_snapshot_id)
        if context.pipeline_run.id != pipeline_run_id:
            raise RawSnapshotPipelineMismatchError(
                raw_snapshot_id,
                context.pipeline_run.id,
                pipeline_run_id,
            )
        if context.pipeline_run.status in TERMINAL_STATUSES:
            raise PipelineRunAlreadyFinalizedError(
                pipeline_run_id,
                context.pipeline_run.status,
                "record_processing",
            )
        if context.pipeline_run.status != PipelineRunStatus.RUNNING.value:
            raise PipelineRunNotRunningError(
                pipeline_run_id,
                context.pipeline_run.status,
            )
        if not context.source_connection.is_active:
            raise SourceConnectionInactiveError(context.source_connection.id)
        return context

    async def _route_record(
        self,
        record: ProcessedSourceRecord,
    ) -> JobProcessingOutcome:
        try:
            await self._new_jobs.create_new_job(
                PersistNewJobCommand(record.observation_id, record.source_record)
            )
            return JobProcessingOutcome.NEW
        except ExistingJobRequiresComparisonError:
            pass

        try:
            await self._unchanged_jobs.apply_unchanged_observation(
                ApplyUnchangedObservationCommand(
                    record.observation_id,
                    record.source_record,
                )
            )
            return JobProcessingOutcome.UNCHANGED
        except ChangedJobRequiresVersioningError:
            await self._changed_jobs.apply_changed_observation(
                ApplyChangedObservationCommand(
                    record.observation_id,
                    record.source_record,
                )
            )
            return JobProcessingOutcome.CHANGED

    async def _quarantine_invalid_record(
        self,
        context: SourceProcessingContext,
        invalid: InvalidProcessedSourceRecord,
    ) -> None:
        await self._persist_quarantine(
            context=context,
            external_job_id=invalid.external_job_id,
            raw_record_locator=invalid.raw_record_locator,
            error_category=invalid.error_category,
            error_code=invalid.error_code,
            error_message=invalid.error_message,
            error_details=invalid.error_details,
        )

    async def _quarantine_record_error(
        self,
        context: SourceProcessingContext,
        record: ProcessedSourceRecord,
        error: Exception,
    ) -> None:
        error_code = getattr(error, "code", None)
        await self._persist_quarantine(
            context=context,
            external_job_id=str(record.source_record.id),
            raw_record_locator=record.raw_record_locator,
            error_category=_record_error_category(error),
            error_code=error_code,
            error_message=str(error),
            error_details={"application_error_code": error_code},
        )

    async def _persist_quarantine(
        self,
        *,
        context: SourceProcessingContext,
        external_job_id: str | None,
        raw_record_locator: str,
        error_category: str,
        error_code: str | None,
        error_message: str,
        error_details: dict[str, object],
    ) -> None:
        record = QuarantineRecord(
            pipeline_run_id=context.pipeline_run.id,
            source_connection_id=context.source_connection.id,
            raw_snapshot_id=context.raw_snapshot.id,
            external_job_id=external_job_id,
            raw_record_locator=raw_record_locator,
            error_category=error_category,
            error_code=error_code,
            error_message=error_message,
            error_details=error_details,
        )
        async with self._session_factory.begin() as session:
            await QuarantineRepository(session).add(record)

        logger.warning(
            "record_quarantined",
            extra={
                "pipeline_run_id": str(context.pipeline_run.id),
                "raw_snapshot_id": str(context.raw_snapshot.id),
                "raw_record_locator": raw_record_locator,
                "external_job_id": external_job_id,
                "error_category": error_category,
            },
        )

    async def _try_finalize_failure(
        self,
        pipeline_run_id: UUID,
        error: Exception,
        metrics: PipelineMetrics,
    ) -> None:
        error_code, error_summary = _classify_pipeline_failure(error)
        try:
            await self._pipeline_runs.fail(
                pipeline_run_id,
                error_code=error_code,
                error_summary=error_summary,
                metrics=metrics,
            )
        except PipelineRunAlreadyFinalizedError:
            logger.info(
                "snapshot_ingestion_failure_not_refinalized",
                extra={"pipeline_run_id": str(pipeline_run_id)},
            )
        except Exception:
            logger.exception(
                "snapshot_ingestion_failure_finalization_failed",
                extra={"pipeline_run_id": str(pipeline_run_id)},
            )


def _classify_pipeline_failure(error: Exception) -> tuple[str, str]:
    if isinstance(error, StorageError):
        return RAW_STORAGE_FAILED, "Stored raw snapshot could not be read."
    if isinstance(error, (GreenhouseResponseShapeError, RawSnapshotIntegrityError)):
        return (
            SOURCE_RESPONSE_INVALID,
            "Stored raw snapshot was not a valid Greenhouse response.",
        )
    if isinstance(
        error,
        (
            NewJobDatabaseError,
            UnchangedJobDatabaseError,
            ChangedJobDatabaseError,
            SQLAlchemyError,
        ),
    ):
        return DATABASE_WRITE_FAILED, "Database processing could not be completed."
    return PIPELINE_INTERNAL_ERROR, "Snapshot record processing could not be completed."


def _record_error_category(error: Exception) -> str:
    if isinstance(error, SourceRecordNormalizationError):
        return "normalization_failed"
    if isinstance(error, SourceRecordHashingError):
        return "canonicalization_failed"
    return "record_domain_validation_failed"
