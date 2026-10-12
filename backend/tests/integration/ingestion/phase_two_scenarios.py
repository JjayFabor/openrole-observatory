"""Fixture scenarios using the production pipeline with mocked HTTP transport."""

import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx

from app.ingestion.locking import PostgresSourceRunLock
from app.ingestion.orchestration import SnapshotIngestionOrchestrator
from app.ingestion.raw_acquisition import RawSnapshotAcquisitionService
from app.ingestion.sync import SourceSyncResult, SourceSyncService
from app.jobs.schemas import CanonicalJobInput
from app.pipeline_runs.service import PipelineRunService
from app.sources.greenhouse.client import GreenhouseClient
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.storage.filesystem import FilesystemObjectStorage
from tests.integration.ingestion.test_source_sync import DatabaseContext, fixture_bytes

INITIAL_TIME = datetime(2026, 10, 1, 12, tzinfo=UTC)


def acceptance_board(
    ids: tuple[int, ...] = (1001, 1002),
    *,
    workplace: str = "remote",
    multiple_changes: bool = False,
    changed_return: bool = False,
    quarantine: str | None = None,
) -> bytes:
    records = json.loads(fixture_bytes("jobs_v1.json"))["jobs"]
    by_id = {record["id"]: record for record in records}
    jobs = []
    for job_id in ids:
        record = copy.deepcopy(by_id.get(job_id, by_id[1001]))
        record["id"] = job_id
        record["metadata"] = [
            {
                "id": 1,
                "name": "acceptance_workplace",
                "value_type": "text",
                "value": workplace if job_id == 1001 else "remote",
            }
        ]
        if job_id == 1001 and multiple_changes:
            record["location"] = {"name": "Manila — Hybrid"}
            record["metadata"].extend(
                [
                    {
                        "id": 2,
                        "name": "acceptance_salary_min",
                        "value_type": "text",
                        "value": "65000.01",
                    },
                    {
                        "id": 3,
                        "name": "acceptance_salary_max",
                        "value_type": "text",
                        "value": "90000.99",
                    },
                    {
                        "id": 4,
                        "name": "acceptance_employment",
                        "value_type": "text",
                        "value": "full_time",
                    },
                ]
            )
        if job_id == 1002 and changed_return:
            record["title"] = "Returning Engineer II"
        if job_id == 1002 and quarantine is not None:
            del record["title" if quarantine == "known" else "id"]
        jobs.append(record)
    return json.dumps({"jobs": jobs}, ensure_ascii=False).encode()


def acceptance_mapper(record: GreenhouseJob) -> CanonicalJobInput:
    """Inject controlled canonical fields; production Greenhouse extraction stays unchanged."""
    canonical = map_greenhouse_job(record)
    values = {entry.name: entry.value for entry in record.metadata or []}

    def text(name: str) -> str | None:
        value = values.get(name)
        assert value is None or isinstance(value, str)
        return value

    minimum, maximum = text("acceptance_salary_min"), text("acceptance_salary_max")
    return canonical.model_copy(
        update={
            "workplace_type": text("acceptance_workplace"),
            "salary_min": Decimal(minimum) if minimum is not None else None,
            "salary_max": Decimal(maximum) if maximum is not None else None,
            "employment_type": text("acceptance_employment"),
        }
    )


class PhaseTwoScenario:
    def __init__(self, context: DatabaseContext, storage_path: Path) -> None:
        self.context = context
        self.now = INITIAL_TIME - timedelta(days=1)
        self.body = b'{"jobs": []}'
        self.failure: str | None = None
        self.requests: list[httpx.Request] = []
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(self._respond)
        )
        self.storage = FilesystemObjectStorage(storage_path)
        pipelines = PipelineRunService(context.session_factory, clock=lambda: self.now)
        self.service = SourceSyncService(
            context.session_factory,
            source_run_lock=PostgresSourceRunLock(context.engine),
            pipeline_run_service=pipelines,
            raw_acquisition_service=RawSnapshotAcquisitionService(
                context.session_factory,
                greenhouse_client=GreenhouseClient(
                    self.http_client, max_attempts=1, clock=lambda: self.now
                ),
                object_storage=self.storage,
            ),
            snapshot_orchestrator=SnapshotIngestionOrchestrator(
                context.session_factory,
                object_storage=self.storage,
                mapper=acceptance_mapper,
                pipeline_run_service=pipelines,
            ),
        )

    def _respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.params["content"] == "true"
        if self.failure == "timeout":
            raise httpx.ReadTimeout("private fixture timeout", request=request)
        if self.failure == "503":
            return httpx.Response(503, content=b"private upstream failure")
        return httpx.Response(
            200, content=self.body, headers={"Content-Type": "application/json"}
        )

    async def sync(
        self, source_id: UUID, body: bytes, *, failure: str | None = None
    ) -> SourceSyncResult:
        self.now += timedelta(days=1)
        self.body, self.failure = body, failure
        return await self.service.sync_source(source_id)

    async def close(self) -> None:
        await self.http_client.aclose()
