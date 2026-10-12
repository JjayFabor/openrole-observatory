from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.pipeline_runs.schemas import PipelineRunRead
from app.raw_snapshots.models import RawSnapshot
from app.raw_snapshots.schemas import RawSnapshotRead


def test_pipeline_run_read_validates_status_from_orm_object() -> None:
    now = datetime.now(UTC)
    pipeline_run = PipelineRun(
        id=uuid4(),
        source_connection_id=uuid4(),
        status=PipelineRunStatus.COMPLETED.value,
        started_at=now,
        completed_at=now,
        records_fetched=42,
        records_valid=41,
        records_quarantined=1,
        jobs_new=5,
        jobs_changed=3,
        jobs_unchanged=33,
        error_code=None,
        error_summary=None,
        created_at=now,
    )

    result = PipelineRunRead.model_validate(pipeline_run)

    assert result.status is PipelineRunStatus.COMPLETED
    assert result.records_fetched == 42


def test_pipeline_run_read_rejects_unsupported_status() -> None:
    now = datetime.now(UTC)
    pipeline_run = PipelineRun(
        id=uuid4(),
        source_connection_id=uuid4(),
        status="unknown",
        started_at=now,
        completed_at=None,
        records_fetched=0,
        records_valid=0,
        records_quarantined=0,
        jobs_new=0,
        jobs_changed=0,
        jobs_unchanged=0,
        error_code=None,
        error_summary=None,
        created_at=now,
    )

    with pytest.raises(ValidationError):
        PipelineRunRead.model_validate(pipeline_run)


def test_raw_snapshot_read_validates_orm_object() -> None:
    now = datetime.now(UTC)
    snapshot = RawSnapshot(
        id=uuid4(),
        pipeline_run_id=uuid4(),
        r2_object_key="bronze/greenhouse/run=test/jobs.json",
        content_hash="a" * 64,
        content_type="application/json",
        content_length_bytes=None,
        record_count=None,
        retrieved_at=now,
        created_at=now,
    )

    result = RawSnapshotRead.model_validate(snapshot)

    assert result.content_hash == "a" * 64
    assert result.content_length_bytes is None
    assert result.record_count is None
