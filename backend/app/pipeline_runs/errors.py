from typing import ClassVar
from uuid import UUID


class PipelineRunError(Exception):
    """Base class for stable pipeline-run application errors."""

    code: ClassVar[str] = "PIPELINE_RUN_ERROR"


class SourceConnectionNotFoundError(PipelineRunError):
    code = "SOURCE_CONNECTION_NOT_FOUND"

    def __init__(self, source_connection_id: UUID) -> None:
        super().__init__(f"Source connection {source_connection_id} was not found.")


class SourceConnectionInactiveError(PipelineRunError):
    code = "SOURCE_CONNECTION_INACTIVE"

    def __init__(self, source_connection_id: UUID) -> None:
        super().__init__(f"Source connection {source_connection_id} is inactive.")


class SourceSyncAlreadyRunningError(PipelineRunError):
    code = "SOURCE_SYNC_ALREADY_RUNNING"

    def __init__(self, source_connection_id: UUID) -> None:
        super().__init__(
            f"Source connection {source_connection_id} already has an active execution."
        )


class PipelineRunNotFoundError(PipelineRunError):
    code = "PIPELINE_RUN_NOT_FOUND"

    def __init__(self, pipeline_run_id: UUID) -> None:
        super().__init__(f"Pipeline run {pipeline_run_id} was not found.")


class PipelineRunInvalidTransitionError(PipelineRunError):
    code = "PIPELINE_INVALID_TRANSITION"

    def __init__(self, pipeline_run_id: UUID, current: str, target: str) -> None:
        super().__init__(
            f"Pipeline run {pipeline_run_id} cannot transition from "
            f"{current!r} to {target!r}."
        )


class PipelineRunAlreadyFinalizedError(PipelineRunInvalidTransitionError):
    code = "PIPELINE_ALREADY_FINALIZED"
