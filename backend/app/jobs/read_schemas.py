from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.jobs.changes import FieldChangeType
from app.jobs.models import JobLifecycleEventType, JobLifecycleStatus
from app.sources.models import SourceProvider


class JobCompanySummary(BaseModel):
    id: UUID
    name: str


class JobSourceSummary(BaseModel):
    id: UUID
    provider: SourceProvider


class CurrentJobVersionSummary(BaseModel):
    id: UUID
    version_number: int
    title: str
    location_text: str | None
    workplace_type: str | None
    employment_type: str | None


class JobListItem(BaseModel):
    id: UUID
    external_job_id: str
    company: JobCompanySummary
    source: JobSourceSummary
    lifecycle_status: JobLifecycleStatus
    first_seen_at: datetime
    last_seen_at: datetime
    absence_first_detected_at: datetime | None
    reappeared_at: datetime | None
    consecutive_absent_runs: int
    current_version: CurrentJobVersionSummary


class JobList(BaseModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int


class JobVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    content_hash: str
    source_observation_id: UUID
    title: str
    description: str | None
    location_text: str | None
    city: str | None
    region: str | None
    country_code: str | None
    workplace_type: str | None
    employment_type: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    salary_period: str | None
    source_url: str
    source_published_at: datetime | None
    source_updated_at: datetime | None
    canonical_metadata: dict[str, JsonValue]
    effective_from: datetime
    effective_to: datetime | None
    is_current: bool
    created_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    source_connection_id: UUID
    external_job_id: str
    lifecycle_status: JobLifecycleStatus
    first_seen_at: datetime
    last_seen_at: datetime
    absence_first_detected_at: datetime | None
    no_longer_observed_at: datetime | None
    reappeared_at: datetime | None
    consecutive_absent_runs: int
    created_at: datetime
    updated_at: datetime


class JobDetailRead(JobRead):
    current_version: JobVersionRead


class JobVersionList(BaseModel):
    items: list[JobVersionRead]
    limit: int
    offset: int


class JobChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    field_name: str
    change_type: FieldChangeType
    old_value: JsonValue
    new_value: JsonValue
    from_version_id: UUID
    to_version_id: UUID
    from_version_number: int
    to_version_number: int
    detected_at: datetime
    created_at: datetime


class JobChangeList(BaseModel):
    items: list[JobChangeRead]
    limit: int
    offset: int


class JobLifecycleEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pipeline_run_id: UUID
    event_type: JobLifecycleEventType
    occurred_at: datetime
    previous_status: JobLifecycleStatus | None
    new_status: JobLifecycleStatus | None
    metadata: dict[str, JsonValue] = Field(validation_alias="event_metadata")
    created_at: datetime


class JobLifecycleRead(BaseModel):
    job_id: UUID
    current_status: JobLifecycleStatus
    first_seen_at: datetime
    last_seen_at: datetime
    absence_first_detected_at: datetime | None
    no_longer_observed_at: datetime | None
    reappeared_at: datetime | None
    consecutive_absent_runs: int
    events: list[JobLifecycleEventRead]
    limit: int
    offset: int
