from typing import ClassVar
from uuid import UUID


class JobLifecycleReconciliationError(Exception):
    """Base class for stable lifecycle evidence and reconciliation errors."""

    code: ClassVar[str] = "JOB_LIFECYCLE_RECONCILIATION_ERROR"


class PresenceReconciliationNotAllowedError(JobLifecycleReconciliationError):
    code = "PRESENCE_RECONCILIATION_NOT_ALLOWED"

    def __init__(
        self,
        pipeline_run_id: UUID,
        status: str,
        *,
        required_status: str = "completed or completed_with_errors",
    ) -> None:
        super().__init__(
            f"Pipeline run {pipeline_run_id} has status {status!r}; presence evidence "
            f"requires {required_status}."
        )


class PresenceDataInvariantError(JobLifecycleReconciliationError):
    code = "PRESENCE_DATA_INVARIANT_FAILED"

    def __init__(self, pipeline_run_id: UUID, reason: str) -> None:
        super().__init__(f"Pipeline run {pipeline_run_id}: {reason}.")


class PresenceReconciliationUnsafeError(JobLifecycleReconciliationError):
    code = "PRESENCE_RECONCILIATION_UNSAFE"

    def __init__(self, pipeline_run_id: UUID, reason: str) -> None:
        super().__init__(
            f"Pipeline run {pipeline_run_id} is unsafe for lifecycle reconciliation: "
            f"{reason}."
        )
