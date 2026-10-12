from datetime import datetime
from typing import ClassVar
from uuid import UUID


class JobObservationProcessingError(Exception):
    """Base class for stable job-observation application errors."""

    code: ClassVar[str] = "JOB_OBSERVATION_PROCESSING_ERROR"


class NewJobPersistenceError(JobObservationProcessingError):
    """Base class for stable new-job application errors."""

    code: ClassVar[str] = "NEW_JOB_PERSISTENCE_ERROR"


class SourceObservationNotFoundError(JobObservationProcessingError):
    code = "SOURCE_OBSERVATION_NOT_FOUND"

    def __init__(self, source_observation_id: UUID) -> None:
        super().__init__(f"Source observation {source_observation_id} was not found.")


class SourceObservationRecordMismatchError(JobObservationProcessingError):
    code = "SOURCE_OBSERVATION_RECORD_MISMATCH"

    def __init__(
        self,
        source_observation_id: UUID,
        observed_external_job_id: str,
        supplied_external_job_id: str,
    ) -> None:
        super().__init__(
            f"Source observation {source_observation_id} represents external job "
            f"{observed_external_job_id!r}, not {supplied_external_job_id!r}."
        )


class UnsupportedJobObservationProviderError(JobObservationProcessingError):
    code = "NEW_JOB_UNSUPPORTED_PROVIDER"

    def __init__(self, source_observation_id: UUID, provider: str) -> None:
        super().__init__(
            f"Source observation {source_observation_id} belongs to unsupported "
            f"provider {provider!r}."
        )


NewJobUnsupportedProviderError = UnsupportedJobObservationProviderError


class SourceObservationAlreadyMaterializedError(JobObservationProcessingError):
    code = "SOURCE_OBSERVATION_ALREADY_MATERIALIZED"

    def __init__(self, source_observation_id: UUID) -> None:
        super().__init__(
            f"Source observation {source_observation_id} already produced a job "
            "version."
        )


class ExistingJobRequiresComparisonError(NewJobPersistenceError):
    code = "EXISTING_JOB_REQUIRES_COMPARISON"

    def __init__(self, source_connection_id: UUID, external_job_id: str) -> None:
        super().__init__(
            f"Job {external_job_id!r} already exists for source connection "
            f"{source_connection_id}; its observation requires comparison."
        )


class SourceRecordNormalizationError(JobObservationProcessingError):
    code = "SOURCE_RECORD_NORMALIZATION_FAILED"

    def __init__(self, source_observation_id: UUID) -> None:
        super().__init__(
            f"Source observation {source_observation_id} could not be normalized."
        )


class NewJobDatabaseError(NewJobPersistenceError):
    code = "NEW_JOB_DATABASE_ERROR"

    def __init__(self, source_observation_id: UUID) -> None:
        super().__init__(
            f"New job for source observation {source_observation_id} could not be "
            "persisted."
        )


class SourceRecordHashingError(JobObservationProcessingError):
    code = "SOURCE_RECORD_HASHING_FAILED"

    def __init__(self, source_observation_id: UUID) -> None:
        super().__init__(
            f"Canonical content for source observation {source_observation_id} "
            "could not be hashed."
        )


class ExistingJobProcessingError(JobObservationProcessingError):
    """Base class for application errors that require an existing job."""

    code: ClassVar[str] = "EXISTING_JOB_PROCESSING_ERROR"


class UnchangedJobPersistenceError(ExistingJobProcessingError):
    """Base class for stable unchanged-job application errors."""

    code: ClassVar[str] = "UNCHANGED_JOB_PERSISTENCE_ERROR"


class NewJobRequiredError(ExistingJobProcessingError):
    code = "NEW_JOB_REQUIRED"

    def __init__(self, source_connection_id: UUID, external_job_id: str) -> None:
        super().__init__(
            f"Job {external_job_id!r} does not exist for source connection "
            f"{source_connection_id}; the new-job path is required."
        )


class CurrentJobVersionMissingError(ExistingJobProcessingError):
    code = "CURRENT_JOB_VERSION_MISSING"

    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"Job {job_id} has no current version.")


class CurrentJobVersionInvariantError(ExistingJobProcessingError):
    code = "CURRENT_JOB_VERSION_INVARIANT_FAILED"

    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"Job {job_id} has more than one current version.")


class ChangedJobRequiresVersioningError(UnchangedJobPersistenceError):
    code = "CHANGED_JOB_REQUIRES_VERSIONING"

    def __init__(self, job_id: UUID) -> None:
        super().__init__(
            f"Job {job_id} has changed canonical content and requires versioning."
        )


class UnchangedJobDatabaseError(UnchangedJobPersistenceError):
    code = "UNCHANGED_JOB_DATABASE_ERROR"

    def __init__(self, source_observation_id: UUID) -> None:
        super().__init__(
            f"Unchanged job for source observation {source_observation_id} could "
            "not be persisted."
        )


class ChangedJobPersistenceError(ExistingJobProcessingError):
    """Base class for stable changed-job application errors."""

    code: ClassVar[str] = "CHANGED_JOB_PERSISTENCE_ERROR"


class JobDiffInvariantError(ChangedJobPersistenceError):
    code = "JOB_DIFF_INVARIANT_FAILED"

    def __init__(self, job_id: UUID) -> None:
        super().__init__(
            f"Job {job_id} has different canonical hashes but no tracked field changes."
        )


class UnchangedJobRequiresFreshnessUpdateError(ChangedJobPersistenceError):
    code = "UNCHANGED_JOB_REQUIRES_FRESHNESS_UPDATE"

    def __init__(self, job_id: UUID) -> None:
        super().__init__(
            f"Job {job_id} has unchanged canonical content and requires the "
            "unchanged-job path."
        )


class StaleJobObservationError(ChangedJobPersistenceError):
    code = "STALE_JOB_OBSERVATION"

    def __init__(
        self,
        source_observation_id: UUID,
        observed_at: datetime,
        latest_known_at: datetime,
    ) -> None:
        super().__init__(
            f"Source observation {source_observation_id} occurred at "
            f"{observed_at.isoformat()}, not after the latest known job state at "
            f"{latest_known_at.isoformat()}."
        )


class HistoricalJobContentAlreadyExistsError(ChangedJobPersistenceError):
    code = "HISTORICAL_JOB_CONTENT_ALREADY_EXISTS"

    def __init__(
        self,
        job_id: UUID,
        historical_version_id: UUID | None = None,
    ) -> None:
        self.historical_version_id = historical_version_id
        version_detail = (
            f" in historical version {historical_version_id}"
            if historical_version_id is not None
            else " in an existing historical version"
        )
        super().__init__(
            f"Job {job_id} already contains this canonical content{version_detail}."
        )


class ChangedJobDatabaseError(ChangedJobPersistenceError):
    code = "CHANGED_JOB_DATABASE_ERROR"

    def __init__(self, source_observation_id: UUID) -> None:
        super().__init__(
            f"Changed job for source observation {source_observation_id} could not "
            "be persisted."
        )
