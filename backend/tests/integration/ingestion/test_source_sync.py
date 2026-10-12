import copy
import json
from collections import deque
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.companies.models import Company
from app.config import get_settings
from app.database.base import Base
from app.database.engine import create_database_engine
from app.ingestion.errors import SourceSyncFailedError
from app.ingestion.locking import PostgresSourceRunLock
from app.ingestion.orchestration import (
    DATABASE_WRITE_FAILED,
    PIPELINE_INTERNAL_ERROR,
    RAW_STORAGE_FAILED,
    SOURCE_RESPONSE_INVALID,
    SnapshotIngestionOrchestrator,
)
from app.ingestion.raw_acquisition import RawSnapshotAcquisitionService
from app.ingestion.sync import SOURCE_REQUEST_TIMEOUT, SourceSyncService
from app.jobs.models import Job, JobVersion
from app.pipeline_runs.errors import (
    SourceConnectionInactiveError,
    SourceConnectionNotFoundError,
    SourceSyncAlreadyRunningError,
)
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.pipeline_runs.query_service import PipelineRunQueryService
from app.pipeline_runs.schemas import PipelineMetrics
from app.pipeline_runs.service import PipelineRunService
from app.quarantine.models import QuarantineRecord
from app.raw_snapshots.models import RawSnapshot
from app.raw_snapshots.repository import RawSnapshotRepository
from app.source_observations.models import SourceObservation
from app.sources.greenhouse.client import GreenhouseFetchResult
from app.sources.greenhouse.errors import GreenhouseTimeoutError
from app.sources.models import SourceConnection, SourceProvider
from app.storage.base import ObjectStorage, StoredObject
from app.storage.errors import StorageWriteError
from app.storage.filesystem import FilesystemObjectStorage
from tests.database_counts import (
    TableCounts,
    capture_table_counts,
    count_rows_since_baseline,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "greenhouse"
FIRST_RETRIEVED_AT = datetime(2026, 10, 6, 9, tzinfo=UTC)
SECOND_RETRIEVED_AT = datetime(2026, 10, 7, 9, tzinfo=UTC)
THIRD_RETRIEVED_AT = datetime(2026, 10, 9, 9, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]
    baseline_counts: TableCounts


class QueueGreenhouseClient:
    def __init__(
        self,
        results: Sequence[GreenhouseFetchResult | Exception],
    ) -> None:
        self._results = deque(results)
        self.board_tokens: list[str] = []

    async def fetch_jobs(self, *, board_token: str) -> GreenhouseFetchResult:
        self.board_tokens.append(board_token)
        if not self._results:
            raise AssertionError("no Greenhouse result remains")
        result = self._results.popleft()
        if isinstance(result, Exception):
            raise result
        return result


class FailingObjectStorage:
    async def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        raise StorageWriteError("simulated storage outage")

    async def get_bytes(self, *, key: str) -> bytes:
        raise AssertionError(f"unexpected object read for {key}")

    async def exists(self, *, key: str) -> bool:
        return False


class CorruptingReadObjectStorage:
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    async def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        return await self._storage.put_bytes(
            key=key,
            data=data,
            content_type=content_type,
        )

    async def get_bytes(self, *, key: str) -> bytes:
        return await self._storage.get_bytes(key=key) + b" "

    async def exists(self, *, key: str) -> bool:
        return await self._storage.exists(key=key)


class CountingPipelineRunService(PipelineRunService):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.fail_calls = 0

    async def fail(
        self,
        pipeline_run_id: UUID,
        *,
        error_code: str,
        error_summary: str,
        metrics: PipelineMetrics | None = None,
    ) -> PipelineRun:
        self.fail_calls += 1
        return await super().fail(
            pipeline_run_id,
            error_code=error_code,
            error_summary=error_summary,
            metrics=metrics,
        )


@pytest_asyncio.fixture
async def database_context() -> AsyncIterator[DatabaseContext]:
    engine = create_database_engine(get_settings().database_url)

    async with engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        baseline_counts = await capture_table_counts(connection)

        try:
            yield DatabaseContext(
                engine,
                connection,
                session_factory,
                baseline_counts,
            )
        finally:
            if transaction.is_active:
                await transaction.rollback()

    await engine.dispose()


def fixture_bytes(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def fetch_result(body: bytes, retrieved_at: datetime) -> GreenhouseFetchResult:
    return GreenhouseFetchResult(
        body=body,
        status_code=200,
        content_type="application/json",
        retrieved_at=retrieved_at,
    )


async def create_source(
    database_context: DatabaseContext,
    *,
    is_active: bool = True,
) -> SourceConnection:
    suffix = uuid4().hex
    async with database_context.session_factory.begin() as session:
        source = SourceConnection(
            company=Company(name=f"Company {suffix}", slug=f"company-{suffix}"),
            provider=SourceProvider.GREENHOUSE.value,
            external_account_key=f"board-{suffix}",
            is_active=is_active,
        )
        session.add(source)
        await session.flush()
    return source


def build_sync_service(
    database_context: DatabaseContext,
    *,
    greenhouse_client: QueueGreenhouseClient,
    object_storage: ObjectStorage,
    pipeline_runs: PipelineRunService | None = None,
) -> SourceSyncService:
    lifecycle = pipeline_runs or PipelineRunService(database_context.session_factory)
    raw_acquisition = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=object_storage,
    )
    processing = SnapshotIngestionOrchestrator(
        database_context.session_factory,
        object_storage=object_storage,
        pipeline_run_service=lifecycle,
    )
    return SourceSyncService(
        database_context.session_factory,
        source_run_lock=PostgresSourceRunLock(database_context.engine),
        pipeline_run_service=lifecycle,
        raw_acquisition_service=raw_acquisition,
        snapshot_orchestrator=processing,
    )


async def count_rows(
    database_context: DatabaseContext,
    model: type[Base],
) -> int:
    return await count_rows_since_baseline(
        database_context.session_factory,
        model,
        database_context.baseline_counts,
    )


async def load_runs(
    database_context: DatabaseContext,
    source_connection_id: UUID,
) -> list[PipelineRun]:
    async with database_context.session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(PipelineRun)
                    .where(PipelineRun.source_connection_id == source_connection_id)
                    .order_by(PipelineRun.started_at)
                )
            ).all()
        )


async def load_source(
    database_context: DatabaseContext,
    source_connection_id: UUID,
) -> SourceConnection:
    async with database_context.session_factory() as session:
        source = await session.get(SourceConnection, source_connection_id)
    assert source is not None
    return source


async def load_job_and_versions(
    database_context: DatabaseContext,
    *,
    source_connection_id: UUID,
    external_job_id: str,
) -> tuple[Job, list[JobVersion]]:
    async with database_context.session_factory() as session:
        job = await session.scalar(
            select(Job).where(
                Job.source_connection_id == source_connection_id,
                Job.external_job_id == external_job_id,
            )
        )
        assert job is not None
        versions = list(
            (
                await session.scalars(
                    select(JobVersion)
                    .where(JobVersion.job_id == job.id)
                    .order_by(JobVersion.version_number)
                )
            ).all()
        )
    return job, versions


@pytest.mark.asyncio
async def test_full_sync_is_idempotent_and_versions_only_changed_jobs(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    fixture_v1 = fixture_bytes("jobs_v1.json")
    fixture_v2 = fixture_bytes("jobs_v2.json")
    client = QueueGreenhouseClient(
        [
            fetch_result(fixture_v1, FIRST_RETRIEVED_AT),
            fetch_result(fixture_v1, SECOND_RETRIEVED_AT),
            fetch_result(fixture_v2, THIRD_RETRIEVED_AT),
        ]
    )
    storage = FilesystemObjectStorage(tmp_path)
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=storage,
    )

    first = await service.sync_source(source.id)
    first_job, first_versions = await load_job_and_versions(
        database_context,
        source_connection_id=source.id,
        external_job_id="1001",
    )
    first_version_state = (
        first_versions[0].id,
        first_versions[0].source_observation_id,
        first_versions[0].content_hash,
        first_versions[0].title,
        first_versions[0].location_text,
        dict(first_versions[0].canonical_metadata),
    )
    assert first_job.first_seen_at == FIRST_RETRIEVED_AT
    assert first_job.last_seen_at == FIRST_RETRIEVED_AT
    assert len(first_versions) == 1

    second = await service.sync_source(source.id)
    repeated_job, repeated_versions = await load_job_and_versions(
        database_context,
        source_connection_id=source.id,
        external_job_id="1001",
    )
    assert repeated_job.id == first_job.id
    assert repeated_job.first_seen_at == FIRST_RETRIEVED_AT
    assert repeated_job.last_seen_at == SECOND_RETRIEVED_AT
    assert len(repeated_versions) == 1
    assert repeated_versions[0].id == first_versions[0].id
    assert await count_rows(database_context, Job) == 4
    assert await count_rows(database_context, JobVersion) == 4
    assert await count_rows(database_context, SourceObservation) == 8

    third = await service.sync_source(source.id)

    assert first.status is PipelineRunStatus.COMPLETED
    assert (first.jobs_new, first.jobs_changed, first.jobs_unchanged) == (4, 0, 0)
    assert second.status is PipelineRunStatus.COMPLETED
    assert (second.jobs_new, second.jobs_changed, second.jobs_unchanged) == (0, 0, 4)
    assert third.status is PipelineRunStatus.COMPLETED
    assert (third.jobs_new, third.jobs_changed, third.jobs_unchanged) == (0, 2, 2)
    assert client.board_tokens == [source.external_account_key] * 3
    assert await count_rows(database_context, PipelineRun) == 3
    assert await count_rows(database_context, RawSnapshot) == 3
    assert await count_rows(database_context, SourceObservation) == 12
    assert await count_rows(database_context, Job) == 4
    assert await count_rows(database_context, JobVersion) == 6
    assert await count_rows(database_context, QuarantineRecord) == 0
    assert len(list(tmp_path.rglob("jobs.json"))) == 3

    changed_job, changed_versions = await load_job_and_versions(
        database_context,
        source_connection_id=source.id,
        external_job_id="1001",
    )
    assert changed_job.id == first_job.id
    assert len(changed_versions) == 2
    first_version, current_version = changed_versions
    assert (
        first_version.id,
        first_version.source_observation_id,
        first_version.content_hash,
        first_version.title,
        first_version.location_text,
        dict(first_version.canonical_metadata),
    ) == first_version_state
    assert first_version.is_current is False
    assert first_version.effective_to == current_version.effective_from
    assert current_version.effective_from == THIRD_RETRIEVED_AT
    assert current_version.is_current is True
    assert current_version.effective_to is None
    assert first_version.content_hash != current_version.content_hash

    async with database_context.session_factory() as session:
        lineage = (
            await session.execute(
                select(
                    JobVersion,
                    SourceObservation,
                    RawSnapshot,
                    PipelineRun,
                    SourceConnection,
                    Company,
                )
                .join(
                    SourceObservation,
                    SourceObservation.id == JobVersion.source_observation_id,
                )
                .join(
                    RawSnapshot,
                    RawSnapshot.id == SourceObservation.raw_snapshot_id,
                )
                .join(PipelineRun, PipelineRun.id == RawSnapshot.pipeline_run_id)
                .join(
                    SourceConnection,
                    SourceConnection.id == PipelineRun.source_connection_id,
                )
                .join(Company, Company.id == SourceConnection.company_id)
                .where(JobVersion.id == current_version.id)
            )
        ).one()

    (
        lineage_version,
        lineage_observation,
        lineage_snapshot,
        lineage_run,
        lineage_source,
        lineage_company,
    ) = lineage
    assert lineage_version.id == current_version.id
    assert lineage_observation.external_job_id == "1001"
    assert lineage_snapshot.pipeline_run_id == lineage_run.id
    assert lineage_run.source_connection_id == lineage_source.id == source.id
    assert lineage_source.company_id == lineage_company.id

    raw_bytes = await storage.get_bytes(key=lineage_snapshot.r2_object_key)
    raw_document = json.loads(raw_bytes)
    locator = lineage_observation.raw_record_locator
    assert locator is not None
    raw_index = int(locator.removeprefix("jobs[").removesuffix("]"))
    assert str(raw_document["jobs"][raw_index]["id"]) == "1001"

    stored_source = await load_source(database_context, source.id)
    assert stored_source.last_attempted_sync_at is not None
    assert stored_source.last_successful_sync_at is not None
    assert stored_source.last_successful_sync_at >= stored_source.last_attempted_sync_at

    query_service = PipelineRunQueryService(database_context.session_factory)
    page = await query_service.list(limit=2, offset=0)
    assert [run.id for run in page] == [third.pipeline_run_id, second.pipeline_run_id]
    detail = await query_service.get(first.pipeline_run_id)
    assert detail is not None
    assert detail.jobs_new == 4

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_partial_success_returns_completed_with_errors(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient(
        [
            fetch_result(
                fixture_bytes("jobs_invalid_record.json"),
                FIRST_RETRIEVED_AT,
            )
        ]
    )
    storage = FilesystemObjectStorage(tmp_path)
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=storage,
    )

    result = await service.sync_source(source.id)

    assert result.status is PipelineRunStatus.COMPLETED_WITH_ERRORS
    assert result.records_fetched == 3
    assert result.records_valid == 2
    assert result.records_quarantined == 1
    assert result.jobs_new == 2
    assert result.records_fetched == result.records_valid + result.records_quarantined
    assert result.records_valid == (
        result.jobs_new + result.jobs_changed + result.jobs_unchanged
    )
    assert await count_rows(database_context, QuarantineRecord) == 1
    assert await count_rows(database_context, Job) == 2

    async with database_context.session_factory() as session:
        quarantine_lineage = (
            await session.execute(
                select(
                    QuarantineRecord,
                    RawSnapshot,
                    PipelineRun,
                    SourceConnection,
                )
                .join(
                    RawSnapshot,
                    RawSnapshot.id == QuarantineRecord.raw_snapshot_id,
                )
                .join(PipelineRun, PipelineRun.id == RawSnapshot.pipeline_run_id)
                .join(
                    SourceConnection,
                    SourceConnection.id == PipelineRun.source_connection_id,
                )
                .where(QuarantineRecord.pipeline_run_id == result.pipeline_run_id)
            )
        ).one()

    quarantine, snapshot, run, stored_source = quarantine_lineage
    assert quarantine.source_connection_id == stored_source.id == source.id
    assert quarantine.raw_snapshot_id == snapshot.id
    assert quarantine.pipeline_run_id == run.id
    assert quarantine.external_job_id is None
    assert quarantine.raw_record_locator == "jobs[1]"
    assert quarantine.error_category == "record_validation_failed"
    assert quarantine.error_details == {"source_record_index": 1}

    raw_bytes = await storage.get_bytes(key=snapshot.r2_object_key)
    malformed_record = json.loads(raw_bytes)["jobs"][1]
    assert "id" not in malformed_record
    assert malformed_record["title"] == "Job Missing Its Greenhouse ID"

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_empty_source_completes_with_zero_metrics_and_releases_lock(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient(
        [fetch_result(b'{"jobs": [], "meta": {"total": 0}}', FIRST_RETRIEVED_AT)]
    )
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    result = await service.sync_source(source.id)

    assert result.status is PipelineRunStatus.COMPLETED
    assert (
        result.records_fetched,
        result.records_valid,
        result.records_quarantined,
        result.jobs_new,
        result.jobs_changed,
        result.jobs_unchanged,
    ) == (0, 0, 0, 0, 0, 0)
    assert await count_rows(database_context, RawSnapshot) == 1
    assert await count_rows(database_context, SourceObservation) == 0
    assert await count_rows(database_context, Job) == 0

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_raw_integrity_failure_fails_without_canonical_processing(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient(
        [fetch_result(fixture_bytes("jobs_v1.json"), FIRST_RETRIEVED_AT)]
    )
    storage = CorruptingReadObjectStorage(FilesystemObjectStorage(tmp_path))
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=storage,
    )

    with pytest.raises(SourceSyncFailedError) as exc_info:
        await service.sync_source(source.id)

    assert exc_info.value.code == SOURCE_RESPONSE_INVALID
    runs = await load_runs(database_context, source.id)
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.FAILED.value
    assert await count_rows(database_context, RawSnapshot) == 1
    assert await count_rows(database_context, SourceObservation) == 0
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, QuarantineRecord) == 0

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_snapshot_persistence_failure_documents_orphan_object(
    database_context: DatabaseContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient(
        [fetch_result(fixture_bytes("jobs_v1.json"), FIRST_RETRIEVED_AT)]
    )

    async def fail_snapshot_insert(
        _repository: RawSnapshotRepository,
        _raw_snapshot: RawSnapshot,
    ) -> RawSnapshot:
        raise SQLAlchemyError("simulated raw snapshot insert failure")

    monkeypatch.setattr(RawSnapshotRepository, "create", fail_snapshot_insert)
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    with pytest.raises(SourceSyncFailedError) as exc_info:
        await service.sync_source(source.id)

    assert exc_info.value.code == DATABASE_WRITE_FAILED
    runs = await load_runs(database_context, source.id)
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.FAILED.value
    assert await count_rows(database_context, RawSnapshot) == 0
    assert len(list(tmp_path.rglob("jobs.json"))) == 1

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_unexpected_top_level_error_fails_run_and_releases_lock(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient([RuntimeError("private programming detail")])
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    with pytest.raises(SourceSyncFailedError) as exc_info:
        await service.sync_source(source.id)

    assert exc_info.value.code == PIPELINE_INTERNAL_ERROR
    assert "private programming detail" not in exc_info.value.safe_message
    runs = await load_runs(database_context, source.id)
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.FAILED.value
    assert runs[0].error_code == PIPELINE_INTERNAL_ERROR
    assert await count_rows(database_context, RawSnapshot) == 0

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_hundred_record_fixture_completes_without_duplicate_outcomes(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    fixture = json.loads(fixture_bytes("jobs_v1.json"))
    template = fixture["jobs"][0]
    jobs: list[dict[str, object]] = []
    for index in range(100):
        record = copy.deepcopy(template)
        record["id"] = 50_000 + index
        record["title"] = f"Synthetic Job {index}"
        record["absolute_url"] = f"https://example.test/jobs/{50_000 + index}"
        jobs.append(record)
    raw_bytes = json.dumps({"jobs": jobs, "meta": {"total": 100}}).encode()
    client = QueueGreenhouseClient([fetch_result(raw_bytes, FIRST_RETRIEVED_AT)])
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    result = await service.sync_source(source.id)

    assert result.status is PipelineRunStatus.COMPLETED
    assert result.records_fetched == result.records_valid == result.jobs_new == 100
    assert result.records_quarantined == 0
    assert await count_rows(database_context, Job) == 100
    assert await count_rows(database_context, JobVersion) == 100
    assert await count_rows(database_context, SourceObservation) == 100


@pytest.mark.asyncio
async def test_upstream_failure_marks_run_failed_and_releases_lock(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient([GreenhouseTimeoutError("private timeout detail")])
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    with pytest.raises(SourceSyncFailedError) as exc_info:
        await service.sync_source(source.id)

    assert exc_info.value.code == SOURCE_REQUEST_TIMEOUT
    runs = await load_runs(database_context, source.id)
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.FAILED.value
    assert runs[0].error_code == SOURCE_REQUEST_TIMEOUT
    assert "private timeout detail" not in (runs[0].error_summary or "")
    assert await count_rows(database_context, RawSnapshot) == 0

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_storage_failure_marks_run_failed_and_releases_lock(
    database_context: DatabaseContext,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient(
        [fetch_result(fixture_bytes("jobs_v1.json"), FIRST_RETRIEVED_AT)]
    )
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FailingObjectStorage(),
    )

    with pytest.raises(SourceSyncFailedError) as exc_info:
        await service.sync_source(source.id)

    assert exc_info.value.code == RAW_STORAGE_FAILED
    runs = await load_runs(database_context, source.id)
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.FAILED.value
    assert await count_rows(database_context, RawSnapshot) == 0

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_processing_failure_is_not_finalized_twice(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient(
        [
            fetch_result(
                fixture_bytes("jobs_invalid_top_level.json"),
                FIRST_RETRIEVED_AT,
            )
        ]
    )
    lifecycle = CountingPipelineRunService(database_context.session_factory)
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
        pipeline_runs=lifecycle,
    )

    with pytest.raises(SourceSyncFailedError) as exc_info:
        await service.sync_source(source.id)

    assert exc_info.value.code == SOURCE_RESPONSE_INVALID
    assert lifecycle.fail_calls == 1
    runs = await load_runs(database_context, source.id)
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.FAILED.value
    assert runs[0].error_code == SOURCE_RESPONSE_INVALID

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        pass


@pytest.mark.asyncio
async def test_lock_contention_creates_no_pipeline_run(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source = await create_source(database_context)
    client = QueueGreenhouseClient(
        [fetch_result(fixture_bytes("jobs_v1.json"), FIRST_RETRIEVED_AT)]
    )
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    async with PostgresSourceRunLock(database_context.engine).hold(source.id):
        with pytest.raises(SourceSyncAlreadyRunningError):
            await service.sync_source(source.id)

    assert await count_rows(database_context, PipelineRun) == 0
    assert client.board_tokens == []


@pytest.mark.asyncio
async def test_lock_for_one_source_does_not_block_another_source(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    source_a = await create_source(database_context)
    source_b = await create_source(database_context)
    client = QueueGreenhouseClient(
        [fetch_result(b'{"jobs": [], "meta": {"total": 0}}', FIRST_RETRIEVED_AT)]
    )
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    async with PostgresSourceRunLock(database_context.engine).hold(source_a.id):
        result = await service.sync_source(source_b.id)

    assert result.source_connection_id == source_b.id
    assert result.status is PipelineRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_missing_and_inactive_sources_create_no_runs(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    inactive_source = await create_source(database_context, is_active=False)
    client = QueueGreenhouseClient([])
    service = build_sync_service(
        database_context,
        greenhouse_client=client,
        object_storage=FilesystemObjectStorage(tmp_path),
    )

    with pytest.raises(SourceConnectionNotFoundError):
        await service.sync_source(uuid4())
    with pytest.raises(SourceConnectionInactiveError):
        await service.sync_source(inactive_source.id)

    assert await count_rows(database_context, PipelineRun) == 0
    assert client.board_tokens == []
