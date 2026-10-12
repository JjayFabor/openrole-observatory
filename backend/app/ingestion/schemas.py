from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.jobs.presence import PresenceUnsafeReason
from app.pipeline_runs.models import PipelineRunStatus


class LifecycleReconciliationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    performed: bool
    skipped_reason: PresenceUnsafeReason | None
    tentative_absences_reset: int
    jobs_reappeared: int
    first_absences_detected: int
    jobs_confirmed_not_observed: int


class SourceSyncRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    lifecycle: LifecycleReconciliationRead | None = None
