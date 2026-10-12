import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.companies.models import Company
from app.config import get_settings
from app.database.engine import create_database_engine
from app.ingestion.errors import (
    PipelineRunNotRunningError,
    PipelineRunSourceMismatchError,
    RawSnapshotAlreadyExistsError,
    RawSnapshotPersistenceError,
    UnsupportedSourceProviderError,
)
from app.ingestion.raw_acquisition import RawSnapshotAcquisitionService
from app.pipeline_runs.errors import (
    PipelineRunNotFoundError,
    SourceConnectionInactiveError,
)
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.raw_snapshots.keys import build_raw_snapshot_key
from app.raw_snapshots.models import RawSnapshot
from app.raw_snapshots.repository import RawSnapshotRepository
from app.sources.greenhouse.client import GreenhouseFetchResult
from app.sources.greenhouse.errors import GreenhouseRequestError
from app.sources.models import SourceConnection, SourceProvider
from app.storage.base import StoredObject
from app.storage.errors import StorageWriteError

RAW_BODY = b'{\n  "jobs": [{"id": 1}]\n}\n'
RETRIEVED_AT = datetime(2026, 10, 6, 11, tzinfo=UTC)


@dataclass(frozen=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class StorageWrite:
    key: str
    data: bytes
    content_type: str


class FakeGreenhouseClient:
    def __init__(
        self,
        *,
        result: GreenhouseFetchResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.board_tokens: list[str] = []

    async def fetch_jobs(self, *, board_token: str) -> GreenhouseFetchResult:
        self.board_tokens.append(board_token)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("fake Greenhouse result was not configured")
        return self.result


class FakeObjectStorage:
    def __init__(
        self,
        *,
        stored_object: StoredObject | None = None,
        error: Exception | None = None,
    ) -> None:
        self.stored_object = stored_object
        self.error = error
        self.writes: list[StorageWrite] = []

    async def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        self.writes.append(StorageWrite(key, data, content_type))
        if self.error is not None:
            raise self.error
        if self.stored_object is None:
            raise AssertionError("fake stored object was not configured")
        return self.stored_object

    async def get_bytes(self, *, key: str) -> bytes:
        raise AssertionError(f"unexpected read for {key}")

    async def exists(self, *, key: str) -> bool:
        raise AssertionError(f"unexpected existence check for {key}")


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

        try:
            yield DatabaseContext(engine, connection, session_factory)
        finally:
            if transaction.is_active:
                await transaction.rollback()

    await engine.dispose()


async def create_pipeline_context(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    status: PipelineRunStatus = PipelineRunStatus.RUNNING,
    provider: str = SourceProvider.GREENHOUSE.value,
    is_active: bool = True,
) -> tuple[SourceConnection, PipelineRun]:
    suffix = uuid4().hex
    attempted_at = datetime(2026, 10, 6, 10, 59, tzinfo=UTC)
    successful_at = datetime(2026, 10, 5, 11, tzinfo=UTC)
    async with session_factory.begin() as session:
        source = SourceConnection(
            company=Company(name=f"Company {suffix}", slug=f"company-{suffix}"),
            provider=provider,
            external_account_key=f"board-{suffix}",
            is_active=is_active,
            last_attempted_sync_at=attempted_at,
            last_successful_sync_at=successful_at,
        )
        run = PipelineRun(
            source_connection=source,
            status=status.value,
            started_at=attempted_at,
        )
        session.add(run)
        await session.flush()
    return source, run


def successful_fetch_result(
    *,
    content_type: str | None = "application/json; charset=utf-8",
) -> GreenhouseFetchResult:
    return GreenhouseFetchResult(
        body=RAW_BODY,
        status_code=200,
        content_type=content_type,
        retrieved_at=RETRIEVED_AT,
    )


def expected_object_key(source_id: UUID, run_id: UUID) -> str:
    return build_raw_snapshot_key(
        provider=SourceProvider.GREENHOUSE.value,
        source_connection_id=source_id,
        pipeline_run_id=run_id,
        retrieved_at=RETRIEVED_AT,
    )


def stored_object_for(key: str, *, content_type: str) -> StoredObject:
    return StoredObject(
        key=key,
        content_type=content_type,
        content_length_bytes=len(RAW_BODY),
        content_hash="b" * 64,
    )


async def load_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    pipeline_run_id: UUID,
) -> RawSnapshot | None:
    async with session_factory() as session:
        return await session.scalar(
            select(RawSnapshot).where(RawSnapshot.pipeline_run_id == pipeline_run_id)
        )


async def load_run(
    session_factory: async_sessionmaker[AsyncSession],
    pipeline_run_id: UUID,
) -> PipelineRun:
    async with session_factory() as session:
        return (
            await session.scalars(
                select(PipelineRun).where(PipelineRun.id == pipeline_run_id)
            )
        ).one()


async def load_source(
    session_factory: async_sessionmaker[AsyncSession],
    source_connection_id: UUID,
) -> SourceConnection:
    async with session_factory() as session:
        return (
            await session.scalars(
                select(SourceConnection).where(
                    SourceConnection.id == source_connection_id
                )
            )
        ).one()


@pytest.mark.asyncio
async def test_successful_acquisition_preserves_bytes_and_persists_metadata(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    object_key = expected_object_key(source.id, run.id)
    fetch_result = successful_fetch_result()
    greenhouse_client = FakeGreenhouseClient(result=fetch_result)
    storage = FakeObjectStorage(
        stored_object=stored_object_for(
            object_key,
            content_type="application/json; charset=utf-8",
        )
    )
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    acquired = await service.acquire(
        pipeline_run_id=run.id,
        source_connection_id=source.id,
    )
    stored_snapshot = await load_snapshot(database_context.session_factory, run.id)
    stored_run = await load_run(database_context.session_factory, run.id)
    stored_source = await load_source(database_context.session_factory, source.id)

    assert greenhouse_client.board_tokens == [source.external_account_key]
    assert storage.writes == [
        StorageWrite(
            key=object_key,
            data=RAW_BODY,
            content_type="application/json; charset=utf-8",
        )
    ]
    assert stored_snapshot is not None
    assert acquired.id == stored_snapshot.id
    assert stored_snapshot.pipeline_run_id == run.id
    assert stored_snapshot.r2_object_key == object_key
    assert stored_snapshot.content_hash == "b" * 64
    assert stored_snapshot.content_length_bytes == len(RAW_BODY)
    assert stored_snapshot.content_type == "application/json; charset=utf-8"
    assert stored_snapshot.retrieved_at == RETRIEVED_AT
    assert stored_snapshot.record_count is None
    assert stored_run.status == PipelineRunStatus.RUNNING.value
    assert stored_run.records_fetched == 0
    assert stored_run.records_valid == 0
    assert stored_source.last_attempted_sync_at == source.last_attempted_sync_at
    assert stored_source.last_successful_sync_at == source.last_successful_sync_at


@pytest.mark.asyncio
async def test_missing_content_type_uses_json_fallback(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    object_key = expected_object_key(source.id, run.id)
    greenhouse_client = FakeGreenhouseClient(
        result=successful_fetch_result(content_type=None)
    )
    storage = FakeObjectStorage(
        stored_object=stored_object_for(
            object_key,
            content_type="application/json",
        )
    )
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    snapshot = await service.acquire(
        pipeline_run_id=run.id,
        source_connection_id=source.id,
    )

    assert storage.writes[0].content_type == "application/json"
    assert snapshot.content_type == "application/json"


@pytest.mark.asyncio
async def test_existing_snapshot_rejects_before_fetch(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    async with database_context.session_factory.begin() as session:
        session.add(
            RawSnapshot(
                pipeline_run_id=run.id,
                r2_object_key=expected_object_key(source.id, run.id),
                content_hash="a" * 64,
                content_type="application/json",
                content_length_bytes=10,
                record_count=None,
                retrieved_at=RETRIEVED_AT,
            )
        )
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage()
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(RawSnapshotAlreadyExistsError) as exc_info:
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=source.id,
        )

    assert exc_info.value.code == "RAW_SNAPSHOT_ALREADY_EXISTS"
    assert greenhouse_client.board_tokens == []
    assert storage.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        PipelineRunStatus.PENDING,
        PipelineRunStatus.COMPLETED,
        PipelineRunStatus.FAILED,
    ],
)
async def test_non_running_pipeline_is_rejected_before_fetch(
    database_context: DatabaseContext,
    status: PipelineRunStatus,
) -> None:
    source, run = await create_pipeline_context(
        database_context.session_factory,
        status=status,
    )
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage()
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(PipelineRunNotRunningError) as exc_info:
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=source.id,
        )

    assert exc_info.value.code == "PIPELINE_RUN_NOT_RUNNING"
    assert greenhouse_client.board_tokens == []
    assert storage.writes == []


@pytest.mark.asyncio
async def test_source_mismatch_is_rejected_before_fetch(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    other_source, _ = await create_pipeline_context(database_context.session_factory)
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage()
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(PipelineRunSourceMismatchError) as exc_info:
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=other_source.id,
        )

    assert exc_info.value.code == "PIPELINE_RUN_SOURCE_MISMATCH"
    assert source.id != other_source.id
    assert greenhouse_client.board_tokens == []
    assert storage.writes == []


@pytest.mark.asyncio
async def test_inactive_source_is_rejected_before_fetch(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(
        database_context.session_factory,
        is_active=False,
    )
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage()
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(SourceConnectionInactiveError):
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=source.id,
        )

    assert greenhouse_client.board_tokens == []
    assert storage.writes == []


@pytest.mark.asyncio
async def test_unsupported_provider_is_rejected_before_fetch(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(
        database_context.session_factory,
        provider="lever",
    )
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage()
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(UnsupportedSourceProviderError) as exc_info:
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=source.id,
        )

    assert exc_info.value.code == "UNSUPPORTED_SOURCE_PROVIDER"
    assert greenhouse_client.board_tokens == []
    assert storage.writes == []


@pytest.mark.asyncio
async def test_missing_pipeline_run_is_rejected_before_fetch(
    database_context: DatabaseContext,
) -> None:
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage()
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(PipelineRunNotFoundError):
        await service.acquire(
            pipeline_run_id=uuid4(),
            source_connection_id=uuid4(),
        )

    assert greenhouse_client.board_tokens == []
    assert storage.writes == []


@pytest.mark.asyncio
async def test_fetch_failure_does_not_store_or_persist_snapshot(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    fetch_error = GreenhouseRequestError("simulated Greenhouse failure")
    greenhouse_client = FakeGreenhouseClient(error=fetch_error)
    storage = FakeObjectStorage()
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(GreenhouseRequestError) as exc_info:
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=source.id,
        )

    assert exc_info.value is fetch_error
    assert storage.writes == []
    assert await load_snapshot(database_context.session_factory, run.id) is None
    assert (await load_run(database_context.session_factory, run.id)).status == (
        PipelineRunStatus.RUNNING.value
    )


@pytest.mark.asyncio
async def test_storage_failure_does_not_persist_snapshot(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    storage_error = StorageWriteError("simulated storage failure")
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage(error=storage_error)
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    with pytest.raises(StorageWriteError) as exc_info:
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=source.id,
        )

    assert exc_info.value is storage_error
    assert len(storage.writes) == 1
    assert await load_snapshot(database_context.session_factory, run.id) is None
    assert (await load_run(database_context.session_factory, run.id)).status == (
        PipelineRunStatus.RUNNING.value
    )


@pytest.mark.asyncio
async def test_database_failure_reports_orphaned_object_without_false_snapshot(
    database_context: DatabaseContext,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    object_key = expected_object_key(source.id, run.id)
    greenhouse_client = FakeGreenhouseClient(result=successful_fetch_result())
    storage = FakeObjectStorage(
        stored_object=stored_object_for(
            object_key,
            content_type="application/json; charset=utf-8",
        )
    )
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=greenhouse_client,
        object_storage=storage,
    )

    async def fail_create(
        _repository: RawSnapshotRepository,
        _raw_snapshot: RawSnapshot,
    ) -> RawSnapshot:
        raise SQLAlchemyError("simulated PostgreSQL insert failure")

    monkeypatch.setattr(RawSnapshotRepository, "create", fail_create)
    caplog.set_level(logging.ERROR, logger="app.ingestion.raw_acquisition")

    with pytest.raises(RawSnapshotPersistenceError) as exc_info:
        await service.acquire(
            pipeline_run_id=run.id,
            source_connection_id=source.id,
        )

    assert exc_info.value.code == "RAW_SNAPSHOT_PERSISTENCE_FAILED"
    assert exc_info.value.object_key == object_key
    assert isinstance(exc_info.value.__cause__, SQLAlchemyError)
    assert len(storage.writes) == 1
    assert await load_snapshot(database_context.session_factory, run.id) is None
    assert (await load_run(database_context.session_factory, run.id)).status == (
        PipelineRunStatus.RUNNING.value
    )
    assert any(
        record.message == "raw_snapshot_persistence_failed"
        and getattr(record, "object_key", None) == object_key
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_success_creates_only_one_snapshot_row(
    database_context: DatabaseContext,
) -> None:
    source, run = await create_pipeline_context(database_context.session_factory)
    object_key = expected_object_key(source.id, run.id)
    service = RawSnapshotAcquisitionService(
        database_context.session_factory,
        greenhouse_client=FakeGreenhouseClient(result=successful_fetch_result()),
        object_storage=FakeObjectStorage(
            stored_object=stored_object_for(
                object_key,
                content_type="application/json; charset=utf-8",
            )
        ),
    )

    await service.acquire(
        pipeline_run_id=run.id,
        source_connection_id=source.id,
    )

    async with database_context.session_factory() as session:
        snapshot_count = await session.scalar(
            select(func.count())
            .select_from(RawSnapshot)
            .where(RawSnapshot.pipeline_run_id == run.id)
        )
    assert snapshot_count == 1
