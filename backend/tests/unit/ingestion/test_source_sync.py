from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.errors import (
    SnapshotRecordProcessingFailedError,
    SourceSyncFailedError,
)
from app.ingestion.sync import SourceSyncService
from app.pipeline_runs.models import PipelineRun
from app.pipeline_runs.schemas import PipelineMetrics
from app.sources.greenhouse.errors import GreenhouseTimeoutError


class NoopLock:
    @asynccontextmanager
    async def hold(self, source_connection_id: UUID) -> AsyncIterator[None]:
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["raw", "records"])
async def test_failure_skips_lifecycle_and_preserves_partial_metrics(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    source_id, run_id = uuid4(), uuid4()
    run = PipelineRun(id=run_id, source_connection_id=source_id, status="running")
    expected_code = (
        "SOURCE_REQUEST_TIMEOUT" if failure_stage == "raw" else "DATABASE_WRITE_FAILED"
    )
    expected_summary = (
        "The source request timed out."
        if failure_stage == "raw"
        else "Database processing could not be completed."
    )
    failed = PipelineRun(
        id=run_id,
        source_connection_id=source_id,
        status="failed",
        error_code=expected_code,
        error_summary=expected_summary,
    )
    metrics = PipelineMetrics(records_fetched=4, records_valid=1, jobs_new=1)
    pipelines, acquisition, processing, lifecycle = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    pipelines.start = AsyncMock(return_value=run)
    pipelines.fail = AsyncMock(return_value=failed)
    acquisition.acquire = AsyncMock(return_value=MagicMock(id=uuid4()))
    if failure_stage == "raw":
        acquisition.acquire.side_effect = GreenhouseTimeoutError("private timeout")
    processing.process_records = AsyncMock(
        side_effect=SnapshotRecordProcessingFailedError(
            metrics=metrics,
            error_code="DATABASE_WRITE_FAILED",
            safe_message="Database processing could not be completed.",
        )
    )
    lifecycle.reconcile_processed_run = AsyncMock()
    service = SourceSyncService(
        cast(async_sessionmaker[AsyncSession], MagicMock()),
        source_run_lock=NoopLock(),
        pipeline_run_service=pipelines,
        raw_acquisition_service=acquisition,
        snapshot_orchestrator=processing,
        lifecycle_reconciliation=lifecycle,
    )
    monkeypatch.setattr(service, "_validate_source", AsyncMock())
    monkeypatch.setattr(service, "_require_run", AsyncMock(return_value=run))

    with pytest.raises(SourceSyncFailedError) as caught:
        await service.sync_source(source_id)

    assert caught.value.code == expected_code
    lifecycle.reconcile_processed_run.assert_not_awaited()
    pipelines.fail.assert_awaited_once_with(
        run_id,
        error_code=expected_code,
        error_summary=expected_summary,
        metrics=PipelineMetrics() if failure_stage == "raw" else metrics,
    )
    if failure_stage == "raw":
        processing.process_records.assert_not_awaited()
