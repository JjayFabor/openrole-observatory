from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RawSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pipeline_run_id: UUID
    r2_object_key: str
    content_hash: str
    content_type: str
    content_length_bytes: int | None
    record_count: int | None
    retrieved_at: datetime
    created_at: datetime
