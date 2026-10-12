from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.pipeline_runs.schemas import PipelineRunRead
from app.sources.models import SourceProvider

NonEmptyString = Annotated[str, Field(min_length=1)]


class SourceConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    provider: SourceProvider
    external_account_key: NonEmptyString
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    is_active: bool = True


class SourceConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    provider: SourceProvider
    external_account_key: str
    configuration: dict[str, JsonValue]
    is_active: bool
    last_successful_sync_at: datetime | None
    last_attempted_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourceHealthRead(BaseModel):
    """Explicit administrative projection; never serialize source configuration."""

    id: UUID
    company_id: UUID
    provider: SourceProvider
    is_active: bool
    last_successful_sync_at: datetime | None
    last_attempted_sync_at: datetime | None
    latest_run: PipelineRunRead | None
