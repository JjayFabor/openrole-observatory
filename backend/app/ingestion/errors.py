from typing import ClassVar
from uuid import UUID

from app.pipeline_runs.schemas import PipelineMetrics


class RawAcquisitionError(Exception):
    """Base class for stable raw-acquisition application errors."""

    code: ClassVar[str] = "RAW_ACQUISITION_ERROR"


class PipelineRunNotRunningError(RawAcquisitionError):
    code = "PIPELINE_RUN_NOT_RUNNING"

    def __init__(self, pipeline_run_id: UUID, status: str) -> None:
        super().__init__(
            f"Pipeline run {pipeline_run_id} must be running, not {status!r}."
        )


class PipelineRunSourceMismatchError(RawAcquisitionError):
    code = "PIPELINE_RUN_SOURCE_MISMATCH"

    def __init__(
        self,
        pipeline_run_id: UUID,
        expected_source_connection_id: UUID,
        supplied_source_connection_id: UUID,
    ) -> None:
        super().__init__(
            f"Pipeline run {pipeline_run_id} belongs to source "
            f"{expected_source_connection_id}, not {supplied_source_connection_id}."
        )


class UnsupportedSourceProviderError(RawAcquisitionError):
    code = "UNSUPPORTED_SOURCE_PROVIDER"

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"This ingestion stage does not support provider {provider!r}."
        )


class RawSnapshotAlreadyExistsError(RawAcquisitionError):
    code = "RAW_SNAPSHOT_ALREADY_EXISTS"

    def __init__(self, pipeline_run_id: UUID) -> None:
        super().__init__(f"Pipeline run {pipeline_run_id} already has a raw snapshot.")


class RawSnapshotPersistenceError(RawAcquisitionError):
    code = "RAW_SNAPSHOT_PERSISTENCE_FAILED"

    def __init__(self, pipeline_run_id: UUID, object_key: str) -> None:
        self.object_key = object_key
        super().__init__(
            f"Raw snapshot metadata for pipeline run {pipeline_run_id} could not "
            f"be persisted after object {object_key!r} was stored."
        )


class SourceProcessingError(Exception):
    """Base class for stable source-record processing errors."""

    code: ClassVar[str] = "SOURCE_PROCESSING_ERROR"


class RawSnapshotNotFoundError(SourceProcessingError):
    code = "RAW_SNAPSHOT_NOT_FOUND"

    def __init__(self, raw_snapshot_id: UUID) -> None:
        super().__init__(f"Raw snapshot {raw_snapshot_id} was not found.")


class RawSnapshotPipelineMismatchError(SourceProcessingError):
    code = "RAW_SNAPSHOT_PIPELINE_MISMATCH"

    def __init__(
        self,
        raw_snapshot_id: UUID,
        expected_pipeline_run_id: UUID,
        supplied_pipeline_run_id: UUID,
    ) -> None:
        super().__init__(
            f"Raw snapshot {raw_snapshot_id} belongs to pipeline run "
            f"{expected_pipeline_run_id}, not {supplied_pipeline_run_id}."
        )


class RawSnapshotIntegrityError(SourceProcessingError):
    code = "RAW_SNAPSHOT_INTEGRITY_FAILED"

    def __init__(self, raw_snapshot_id: UUID, reason: str) -> None:
        super().__init__(f"Raw snapshot {raw_snapshot_id} failed integrity: {reason}.")


class RawSnapshotAlreadyProcessedError(SourceProcessingError):
    code = "RAW_SNAPSHOT_ALREADY_PROCESSED"

    def __init__(self, raw_snapshot_id: UUID) -> None:
        super().__init__(f"Raw snapshot {raw_snapshot_id} was already processed.")


class SnapshotIngestionError(Exception):
    """Base class for record-processing orchestration errors."""

    code: ClassVar[str] = "SNAPSHOT_INGESTION_ERROR"


class PipelineMetricsInvariantError(SnapshotIngestionError):
    code = "PIPELINE_METRICS_INVARIANT_FAILED"

    def __init__(self, reason: str) -> None:
        super().__init__(f"Pipeline metrics are inconsistent: {reason}.")


class SourceSyncFailedError(Exception):
    """A source sync created a run but could not complete successfully."""

    def __init__(
        self,
        *,
        source_connection_id: UUID,
        pipeline_run_id: UUID,
        error_code: str,
        safe_message: str,
    ) -> None:
        self.source_connection_id = source_connection_id
        self.pipeline_run_id = pipeline_run_id
        self.code = error_code
        self.safe_message = safe_message
        super().__init__(safe_message)


class SnapshotRecordProcessingFailedError(Exception):
    """Carry partial record metrics to the owner of terminal run finalization."""

    def __init__(
        self, *, metrics: PipelineMetrics, error_code: str, safe_message: str
    ) -> None:
        self.metrics = metrics
        self.code = error_code
        self.safe_message = safe_message
        super().__init__(safe_message)
