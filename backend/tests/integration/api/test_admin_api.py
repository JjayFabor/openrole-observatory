from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_pipeline_run_query_service,
    get_source_sync_service,
)
from app.config import Settings
from app.ingestion.errors import SourceSyncFailedError
from app.ingestion.orchestration import (
    PIPELINE_INTERNAL_ERROR,
    RAW_STORAGE_FAILED,
    SOURCE_RESPONSE_INVALID,
)
from app.ingestion.schemas import SourceSyncRead
from app.ingestion.sync import (
    SOURCE_REQUEST_FAILED,
    SOURCE_REQUEST_TIMEOUT,
    SourceSyncResult,
    SourceSyncService,
)
from app.jobs.lifecycle_reconciliation import LifecycleReconciliationResult
from app.jobs.presence import PresenceUnsafeReason
from app.main import create_app
from app.pipeline_runs.errors import (
    SourceConnectionInactiveError,
    SourceConnectionNotFoundError,
    SourceSyncAlreadyRunningError,
)
from app.pipeline_runs.models import PipelineRunStatus
from app.pipeline_runs.query_service import PipelineRunQueryService
from app.pipeline_runs.schemas import PipelineRunRead

NOW = datetime(2026, 10, 10, 10, tzinfo=UTC)


class StubSourceSyncService:
    def __init__(
        self,
        *,
        result: SourceSyncResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.source_ids: list[UUID] = []

    async def sync_source(self, source_connection_id: UUID) -> SourceSyncResult:
        self.source_ids.append(source_connection_id)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("stub sync result was not configured")
        return self.result


class StubPipelineRunQueryService:
    def __init__(self, runs: list[PipelineRunRead]) -> None:
        self.runs = runs
        self.list_arguments: list[tuple[int, int]] = []
        self.detail_ids: list[UUID] = []

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        source_connection_id: UUID | None = None,
        status: PipelineRunStatus | None = None,
    ) -> list[PipelineRunRead]:
        self.list_arguments.append((limit, offset))
        runs = [
            run
            for run in self.runs
            if (
                source_connection_id is None
                or run.source_connection_id == source_connection_id
            )
            and (status is None or run.status == status)
        ]
        return runs[offset : offset + limit]

    async def get(self, pipeline_run_id: UUID) -> PipelineRunRead | None:
        self.detail_ids.append(pipeline_run_id)
        return next((run for run in self.runs if run.id == pipeline_run_id), None)


def sync_result(
    *,
    status: PipelineRunStatus = PipelineRunStatus.COMPLETED,
) -> SourceSyncResult:
    return SourceSyncResult(
        pipeline_run_id=uuid4(),
        source_connection_id=uuid4(),
        status=status,
        records_fetched=3,
        records_valid=2,
        records_quarantined=1,
        jobs_new=1,
        jobs_changed=1,
        jobs_unchanged=0,
        started_at=NOW,
        completed_at=NOW,
    )


def pipeline_run_read() -> PipelineRunRead:
    return PipelineRunRead(
        id=uuid4(),
        source_connection_id=uuid4(),
        status=PipelineRunStatus.COMPLETED,
        started_at=NOW,
        completed_at=NOW,
        records_fetched=3,
        records_valid=3,
        records_quarantined=0,
        jobs_new=3,
        jobs_changed=0,
        jobs_unchanged=0,
        error_code=None,
        error_summary=None,
        created_at=NOW,
    )


def configured_app(
    sync_service: StubSourceSyncService,
    query_service: StubPipelineRunQueryService | None = None,
) -> FastAPI:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://127.0.0.1:1/openrole",
        _env_file=None,
    )
    application = create_app(settings)
    queries = query_service or StubPipelineRunQueryService([])
    application.dependency_overrides[get_source_sync_service] = lambda: cast(
        SourceSyncService,
        sync_service,
    )
    application.dependency_overrides[get_pipeline_run_query_service] = lambda: cast(
        PipelineRunQueryService,
        queries,
    )
    return application


def test_source_sync_result_maps_to_api_schema() -> None:
    result = sync_result(status=PipelineRunStatus.COMPLETED_WITH_ERRORS)

    response = SourceSyncRead.model_validate(result)

    assert response.pipeline_run_id == result.pipeline_run_id
    assert response.status is PipelineRunStatus.COMPLETED_WITH_ERRORS
    assert response.records_quarantined == 1


@pytest.mark.parametrize(
    "terminal_status",
    [PipelineRunStatus.COMPLETED, PipelineRunStatus.COMPLETED_WITH_ERRORS],
)
def test_sync_endpoint_returns_final_success_result(
    terminal_status: PipelineRunStatus,
) -> None:
    result = sync_result(status=terminal_status)
    service = StubSourceSyncService(result=result)

    with TestClient(configured_app(service)) as client:
        response = client.post(f"/api/v1/sources/{result.source_connection_id}/sync")

    assert response.status_code == 200
    assert response.json()["pipeline_run_id"] == str(result.pipeline_run_id)
    assert response.json()["status"] == terminal_status.value
    assert service.source_ids == [result.source_connection_id]


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            SourceConnectionNotFoundError(uuid4()),
            404,
            "SOURCE_CONNECTION_NOT_FOUND",
        ),
        (
            SourceConnectionInactiveError(uuid4()),
            409,
            "SOURCE_CONNECTION_INACTIVE",
        ),
        (
            SourceSyncAlreadyRunningError(uuid4()),
            409,
            "SOURCE_SYNC_ALREADY_RUNNING",
        ),
    ],
)
def test_sync_endpoint_maps_source_state_errors(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    source_id = uuid4()
    service = StubSourceSyncService(error=error)

    with TestClient(configured_app(service)) as client:
        response = client.post(
            f"/api/v1/sources/{source_id}/sync",
            headers={"X-Request-ID": "request-123"},
        )

    assert response.status_code == expected_status
    assert response.json() == {
        "error": {
            "code": expected_code,
            "message": response.json()["error"]["message"],
            "request_id": "request-123",
        }
    }


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        (SOURCE_REQUEST_TIMEOUT, 504),
        (SOURCE_REQUEST_FAILED, 502),
        (SOURCE_RESPONSE_INVALID, 502),
        (RAW_STORAGE_FAILED, 503),
        (PIPELINE_INTERNAL_ERROR, 500),
    ],
)
def test_sync_endpoint_maps_terminal_sync_failures(
    error_code: str,
    expected_status: int,
) -> None:
    source_id = uuid4()
    error = SourceSyncFailedError(
        source_connection_id=source_id,
        pipeline_run_id=uuid4(),
        error_code=error_code,
        safe_message="Safe operational summary.",
    )

    with TestClient(configured_app(StubSourceSyncService(error=error))) as client:
        response = client.post(f"/api/v1/sources/{source_id}/sync")

    assert response.status_code == expected_status
    assert response.json()["error"] == {
        "code": error_code,
        "message": "Safe operational summary.",
        "request_id": None,
    }


def test_sync_endpoint_hides_unexpected_exception() -> None:
    source_id = uuid4()
    service = StubSourceSyncService(error=RuntimeError("private implementation detail"))

    with TestClient(configured_app(service)) as client:
        response = client.post(f"/api/v1/sources/{source_id}/sync")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == PIPELINE_INTERNAL_ERROR
    assert "private implementation detail" not in response.text


def test_pipeline_run_list_and_detail_endpoints() -> None:
    run = pipeline_run_read()
    queries = StubPipelineRunQueryService([run])
    application = configured_app(
        StubSourceSyncService(result=sync_result()),
        queries,
    )

    with TestClient(application) as client:
        list_response = client.get("/api/v1/pipeline-runs?limit=10&offset=0")
        detail_response = client.get(f"/api/v1/pipeline-runs/{run.id}")
        missing_response = client.get(f"/api/v1/pipeline-runs/{uuid4()}")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == str(run.id)
    assert list_response.json()["limit"] == 10
    assert queries.list_arguments == [(10, 0)]
    assert detail_response.status_code == 200
    assert detail_response.json()["jobs_new"] == 3
    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "PIPELINE_RUN_NOT_FOUND"


@pytest.mark.parametrize("performed", [True, False])
def test_sync_response_preserves_metrics_and_adds_lifecycle_summary(
    performed: bool,
) -> None:
    lifecycle = LifecycleReconciliationResult(
        performed=performed,
        skipped_reason=None
        if performed
        else PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS,
        first_absences_detected=2 if performed else 0,
    )
    result = replace(sync_result(), lifecycle=lifecycle)
    application = configured_app(StubSourceSyncService(result=result))
    response = TestClient(application).post(
        f"/api/v1/sources/{result.source_connection_id}/sync"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["records_fetched"] == result.records_fetched
    assert payload["jobs_new"] == result.jobs_new
    assert payload["lifecycle"]["performed"] is performed
    assert payload["lifecycle"]["skipped_reason"] == (
        None if performed else "unidentified_quarantine_records"
    )
    assert payload["lifecycle"]["first_absences_detected"] == (2 if performed else 0)
