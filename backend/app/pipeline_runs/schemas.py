from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.pipeline_runs.models import PipelineRunStatus


class PipelineMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    records_fetched: int = Field(default=0, ge=0)
    records_valid: int = Field(default=0, ge=0)
    records_quarantined: int = Field(default=0, ge=0)
    jobs_new: int = Field(default=0, ge=0)
    jobs_changed: int = Field(default=0, ge=0)
    jobs_unchanged: int = Field(default=0, ge=0)


class PipelineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_connection_id: UUID
    status: PipelineRunStatus
    started_at: datetime
    completed_at: datetime | None
    records_fetched: int
    records_valid: int
    records_quarantined: int
    jobs_new: int
    jobs_changed: int
    jobs_unchanged: int
    error_code: str | None
    error_summary: str | None
    created_at: datetime


class PipelineRunList(BaseModel):
    items: list[PipelineRunRead]
    limit: int
    offset: int
