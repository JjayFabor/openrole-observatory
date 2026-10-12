from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, JsonValue

from app.quarantine.models import QuarantineStatus
from app.sources.models import SourceProvider


class QuarantineSourceSummary(BaseModel):
    provider: SourceProvider
    company_name: str


class QuarantineListItem(BaseModel):
    id: UUID
    pipeline_run_id: UUID
    source_connection_id: UUID
    raw_snapshot_id: UUID
    external_job_id: str | None
    raw_record_locator: str | None
    error_category: str
    error_code: str | None
    error_message: str
    status: QuarantineStatus
    created_at: datetime
    resolved_at: datetime | None
    source: QuarantineSourceSummary


class QuarantineRecordDetail(QuarantineListItem):
    error_details: dict[str, JsonValue]


class QuarantineList(BaseModel):
    items: list[QuarantineListItem]
    total: int
    limit: int
    offset: int
