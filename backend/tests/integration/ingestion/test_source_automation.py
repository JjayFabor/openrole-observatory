import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.cli.automate_greenhouse import AUTOMATION_LOCK_SCOPE, run
from app.companies.models import Company
from app.ingestion.locking import PostgresSourceRunLock
from app.ingestion.source_automation import discover_boards, synchronize_active_sources
from app.ingestion.sync import SourceSyncResult
from app.jobs.models import Job, JobVersion
from app.pipeline_runs.errors import SourceSyncAlreadyRunningError
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.sources.greenhouse.client import GreenhouseClient
from app.sources.greenhouse.discovery import DEFAULT_DIRECTORY_URL
from app.sources.models import SourceConnection
from app.storage.filesystem import FilesystemObjectStorage
from tests.integration.ingestion.phase_two_scenarios import (
    PhaseTwoScenario,
    acceptance_board,
)
from tests.integration.ingestion.test_source_sync import (
    DatabaseContext,
    FailingObjectStorage,
    create_source,
)
from tests.integration.ingestion.test_source_sync import (
    database_context as database_context,
)
from tests.test_greenhouse_discovery import candidate, catalogue


async def no_sleep(_: float) -> None:
    return None


class DiscoveryTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.directory_status = 200
        self.bad_token: str | None = None
        self.requests: list[httpx.Request] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(self.directory_status, content=self.body)
        token = request.url.path.rsplit("/", 1)[-1]
        if token == self.bad_token:
            return httpx.Response(404)
        assert not request.url.query
        return httpx.Response(200, json={"name": f"Official {token}"})


@pytest.mark.asyncio
async def test_discovery_admission_raw_lineage_and_repeat_preserve_disabled_sources(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    suffix = uuid4().hex
    tokens = [f"a-{suffix}", f"b-{suffix}"]
    transport = DiscoveryTransport(
        catalogue(*(candidate(t, name="Untrusted") for t in tokens))
    )
    storage = FilesystemObjectStorage(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport.respond)
    ) as client:
        greenhouse = GreenhouseClient(client, max_attempts=1)
        first = await discover_boards(
            database_context.session_factory,
            http_client=client,
            greenhouse=greenhouse,
            storage=storage,
            directory_url=DEFAULT_DIRECTORY_URL,
            cycle_id=uuid4(),
            max_new_sources=1,
            sleep=no_sleep,
        )
        assert (first.created, first.deferred) == (1, 1)
        assert first.directory_object_key is not None
        assert await storage.get_bytes(key=first.directory_object_key) == transport.body
        async with database_context.session_factory.begin() as session:
            source = (
                await session.scalars(
                    select(SourceConnection).where(
                        SourceConnection.external_account_key == tokens[0]
                    )
                )
            ).one()
            company = await session.get(Company, source.company_id)
            assert company is not None and company.name == f"Official {tokens[0]}"
            evidence = source.configuration["discovery"]
            assert isinstance(evidence, dict)
            native_key = evidence["board_object_key"]
            assert isinstance(native_key, str)
            native_body = await storage.get_bytes(key=native_key)
            assert evidence["board_sha256"] == hashlib.sha256(native_body).hexdigest()
            assert (
                evidence["directory_sha256"]
                == hashlib.sha256(transport.body).hexdigest()
            )
            original_configuration = source.configuration
            source.is_active = False
            company.name = "Operator's company name"
            original_id = source.id
        second = await discover_boards(
            database_context.session_factory,
            http_client=client,
            greenhouse=greenhouse,
            storage=storage,
            directory_url=DEFAULT_DIRECTORY_URL,
            cycle_id=uuid4(),
            max_new_sources=1,
            sleep=no_sleep,
        )
        assert (second.created, second.existing, second.deferred) == (1, 1, 0)
        third = await discover_boards(
            database_context.session_factory,
            http_client=client,
            greenhouse=greenhouse,
            storage=storage,
            directory_url=DEFAULT_DIRECTORY_URL,
            cycle_id=uuid4(),
            max_new_sources=25,
            sleep=no_sleep,
        )
        assert (third.created, third.existing) == (0, 2)
    async with database_context.session_factory() as session:
        original = await session.get(SourceConnection, original_id)
        assert original is not None and not original.is_active
        assert original.configuration == original_configuration
        company = await session.get(Company, original.company_id)
        assert company is not None and company.name == "Operator's company name"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SourceConnection)
                .where(SourceConnection.external_account_key.in_(tokens))
            )
            == 2
        )
    assert (
        len([r for r in transport.requests if r.url.host == "boards-api.greenhouse.io"])
        == 2
    )


@pytest.mark.asyncio
async def test_discovery_failed_board_does_not_block_others_and_storage_is_required(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    suffix = uuid4().hex
    bad, good = f"a-{suffix}", f"b-{suffix}"
    transport = DiscoveryTransport(catalogue(candidate(bad), candidate(good)))
    transport.bad_token = bad
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport.respond)
    ) as client:
        blocked = await discover_boards(
            database_context.session_factory,
            storage=FailingObjectStorage(),
            cycle_id=uuid4(),
            http_client=client,
            greenhouse=GreenhouseClient(client, max_attempts=1),
            directory_url=DEFAULT_DIRECTORY_URL,
            max_new_sources=25,
            sleep=no_sleep,
        )
        assert blocked.created == 0
        assert [e.code for e in blocked.failures] == ["DISCOVERY_STORAGE_FAILED"]
        report = await discover_boards(
            database_context.session_factory,
            storage=FilesystemObjectStorage(tmp_path),
            cycle_id=uuid4(),
            http_client=client,
            greenhouse=GreenhouseClient(client, max_attempts=1),
            directory_url=DEFAULT_DIRECTORY_URL,
            max_new_sources=25,
            sleep=no_sleep,
        )
    assert report.created == 1
    assert [(e.token, e.code) for e in report.failures] == [
        (bad, "BOARD_REQUEST_FAILED")
    ]
    async with database_context.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SourceConnection)
                .where(SourceConnection.external_account_key == bad)
            )
            == 0
        )


def completed(source_id: UUID) -> SourceSyncResult:
    return SourceSyncResult(
        pipeline_run_id=uuid4(),
        source_connection_id=source_id,
        status=PipelineRunStatus.COMPLETED,
        records_fetched=0,
        records_valid=0,
        records_quarantined=0,
        jobs_new=0,
        jobs_changed=0,
        jobs_unchanged=0,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_batch_pagination_skips_inactive_and_continues_busy_and_unexpected_failures(
    database_context: DatabaseContext,
) -> None:
    sources = [await create_source(database_context) for _ in range(5)]
    disabled = await create_source(database_context, is_active=False)
    visited: list[UUID] = []

    async def sync(source_id: UUID) -> SourceSyncResult:
        visited.append(source_id)
        if source_id == sources[0].id:
            raise SourceSyncAlreadyRunningError(source_id)
        if source_id == sources[1].id:
            raise RuntimeError("private unexpected error")
        return completed(source_id)

    report = await synchronize_active_sources(
        database_context.session_factory, sync, batch_size=2, sleep=no_sleep
    )
    assert {s.id for s in sources}.issubset(visited)
    assert disabled.id not in visited
    assert len(visited) == len(set(visited)) == report.attempted
    assert report.busy_skipped == 1
    assert report.completed == len(visited) - 2
    assert [e.code for e in report.failures] == ["AUTOMATION_SYNC_FAILED"]


@pytest.mark.asyncio
async def test_scheduled_pipeline_is_idempotent_and_outages_preserve_present_jobs(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    sources = [await create_source(database_context) for _ in range(2)]
    source_ids = {s.id for s in sources}
    scenario = PhaseTwoScenario(database_context, tmp_path)
    failed: UUID | None = None

    async def sync(source_id: UUID) -> SourceSyncResult:
        if source_id not in source_ids:
            return completed(source_id)
        return await scenario.sync(
            source_id,
            acceptance_board(),
            failure="503" if source_id == failed else None,
        )

    try:
        first = await synchronize_active_sources(
            database_context.session_factory, sync, sleep=no_sleep
        )
        assert first.jobs_new == 4 and not first.failures
        second = await synchronize_active_sources(
            database_context.session_factory, sync, sleep=no_sleep
        )
        assert second.jobs_new == second.jobs_changed == 0
        assert second.jobs_unchanged == 4
        failed = sources[0].id
        outage = DiscoveryTransport(b"private catalogue outage")
        outage.directory_status = 503
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(outage.respond)
        ) as client:
            discovery = await discover_boards(
                database_context.session_factory,
                http_client=client,
                greenhouse=GreenhouseClient(client, max_attempts=1),
                storage=scenario.storage,
                directory_url=DEFAULT_DIRECTORY_URL,
                cycle_id=uuid4(),
                max_new_sources=25,
                sleep=no_sleep,
            )
        assert discovery.created == 0 and discovery.failures
        third = await synchronize_active_sources(
            database_context.session_factory, sync, sleep=no_sleep
        )
        assert len(third.failures) == 1 and third.jobs_unchanged == 2
        async with database_context.session_factory() as session:
            jobs = list(
                await session.scalars(
                    select(Job).where(Job.source_connection_id.in_(source_ids))
                )
            )
            assert len(jobs) == 4
            assert all(job.lifecycle_status == "observed" for job in jobs)
            assert all(job.consecutive_absent_runs == 0 for job in jobs)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(JobVersion)
                    .where(JobVersion.job_id.in_([j.id for j in jobs]))
                )
                == 4
            )
            statuses = list(
                await session.scalars(
                    select(PipelineRun.status).where(
                        PipelineRun.source_connection_id.in_(source_ids)
                    )
                )
            )
            assert statuses.count("failed") == 1 and statuses.count("completed") == 5
    finally:
        await scenario.close()


@pytest.mark.asyncio
async def test_global_automation_lock_skips_cycle_before_any_network_request(
    database_context: DatabaseContext,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with PostgresSourceRunLock(database_context.engine).hold(
        AUTOMATION_LOCK_SCOPE
    ):
        assert (
            await run(
                directory_url=DEFAULT_DIRECTORY_URL, max_new_sources=25, request_delay=0
            )
            == 0
        )
    assert json.loads(capsys.readouterr().out)["code"] == "AUTOMATION_ALREADY_RUNNING"
