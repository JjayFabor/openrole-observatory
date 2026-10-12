import hashlib
import json
from collections.abc import AsyncIterator
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
from app.ingestion.errors import (
    PipelineRunNotRunningError,
    RawSnapshotAlreadyProcessedError,
    RawSnapshotIntegrityError,
    RawSnapshotNotFoundError,
    RawSnapshotPipelineMismatchError,
    UnsupportedSourceProviderError,
)
from app.ingestion.source_processing import (
    DUPLICATE_SOURCE_IDENTIFIER,
    RECORD_VALIDATION_FAILED,
    SourceRecordProcessingService,
)
from app.jobs.models import Job, JobVersion
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.quarantine.models import QuarantineRecord
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.source_observations.repository import SourceObservationRepository
from app.source_observations.source_records import compute_source_content_hash
from app.sources.greenhouse.errors import GreenhouseResponseShapeError
from app.sources.models import SourceConnection, SourceProvider
from app.storage.base import ObjectStorage, StoredObject
from app.storage.errors import ObjectNotFoundError
from app.storage.filesystem import FilesystemObjectStorage
from tests.database_counts import (
    TableCounts,
    capture_table_counts,
    count_rows_since_baseline,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "greenhouse"
RETRIEVED_AT = datetime(2026, 10, 6, 11, tzinfo=UTC)


@dataclass(frozen=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]
    baseline_counts: TableCounts


class RecordingObjectStorage:
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage
        self.read_keys: list[str] = []

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
        self.read_keys.append(key)
        return await self._storage.get_bytes(key=key)

    async def exists(self, *, key: str) -> bool:
        return await self._storage.exists(key=key)


@dataclass(frozen=True)
class SnapshotSetup:
    source: SourceConnection
    pipeline_run: PipelineRun
    raw_snapshot: RawSnapshot
    storage: RecordingObjectStorage
    raw_bytes: bytes


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


async def create_snapshot_setup(
    database_context: DatabaseContext,
    storage_root: Path,
    raw_bytes: bytes,
    *,
    status: PipelineRunStatus = PipelineRunStatus.RUNNING,
    provider: str = SourceProvider.GREENHOUSE.value,
    store_object: bool = True,
    content_hash: str | None = None,
    content_length_bytes: int | None = None,
    record_count: int | None = None,
) -> SnapshotSetup:
    suffix = uuid4().hex
    storage = RecordingObjectStorage(FilesystemObjectStorage(storage_root))
    object_key = f"bronze/tests/{suffix}/jobs.json"
    stored_object: StoredObject | None = None
    if store_object:
        stored_object = await storage.put_bytes(
            key=object_key,
            data=raw_bytes,
            content_type="application/json",
        )

    resolved_hash = content_hash
    if resolved_hash is None:
        resolved_hash = (
            stored_object.content_hash
            if stored_object is not None
            else hashlib.sha256(raw_bytes).hexdigest()
        )
    resolved_length = content_length_bytes
    if resolved_length is None:
        resolved_length = len(raw_bytes)

    async with database_context.session_factory.begin() as session:
        source = SourceConnection(
            company=Company(name=f"Company {suffix}", slug=f"company-{suffix}"),
            provider=provider,
            external_account_key=f"board-{suffix}",
        )
        pipeline_run = PipelineRun(
            source_connection=source,
            status=status.value,
            started_at=RETRIEVED_AT,
        )
        raw_snapshot = RawSnapshot(
            pipeline_run=pipeline_run,
            r2_object_key=object_key,
            content_hash=resolved_hash,
            content_type="application/json",
            content_length_bytes=resolved_length,
            record_count=record_count,
            retrieved_at=RETRIEVED_AT,
        )
        session.add(raw_snapshot)
        await session.flush()

    return SnapshotSetup(source, pipeline_run, raw_snapshot, storage, raw_bytes)


def create_service(
    database_context: DatabaseContext,
    storage: ObjectStorage,
) -> SourceRecordProcessingService:
    return SourceRecordProcessingService(
        database_context.session_factory,
        object_storage=storage,
    )


async def load_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot_id: UUID,
) -> RawSnapshot:
    async with session_factory() as session:
        return (
            await session.scalars(
                select(RawSnapshot).where(RawSnapshot.id == snapshot_id)
            )
        ).one()


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


async def load_observations(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot_id: UUID,
) -> list[SourceObservation]:
    async with session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(SourceObservation)
                    .where(SourceObservation.raw_snapshot_id == snapshot_id)
                    .order_by(SourceObservation.raw_record_locator)
                )
            ).all()
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


@pytest.mark.asyncio
async def test_valid_fixture_creates_observations_with_complete_lineage(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_v1.json"),
    )
    service = create_service(database_context, setup.storage)

    result = await service.process_raw_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    snapshot = await load_snapshot(
        database_context.session_factory,
        setup.raw_snapshot.id,
    )
    pipeline_run = await load_run(
        database_context.session_factory,
        setup.pipeline_run.id,
    )
    observations = await load_observations(
        database_context.session_factory,
        setup.raw_snapshot.id,
    )
    decoded = json.loads(setup.raw_bytes)

    assert result.records_fetched == 4
    assert result.records_valid == 4
    assert result.records_invalid == 0
    assert [record.source_record.id for record in result.valid_records] == [
        1001,
        1002,
        1003,
        1004,
    ]
    assert [record.raw_record_locator for record in result.valid_records] == [
        "jobs[0]",
        "jobs[1]",
        "jobs[2]",
        "jobs[3]",
    ]
    assert result.invalid_records == ()
    assert snapshot.record_count == 4
    assert len(observations) == 4
    assert [observation.pipeline_run_id for observation in observations] == [
        setup.pipeline_run.id
    ] * 4
    assert [observation.source_connection_id for observation in observations] == [
        setup.source.id
    ] * 4
    assert [observation.raw_snapshot_id for observation in observations] == [
        setup.raw_snapshot.id
    ] * 4
    assert [observation.external_job_id for observation in observations] == [
        "1001",
        "1002",
        "1003",
        "1004",
    ]
    assert [observation.raw_record_locator for observation in observations] == [
        "jobs[0]",
        "jobs[1]",
        "jobs[2]",
        "jobs[3]",
    ]
    assert all(observation.observed_at == RETRIEVED_AT for observation in observations)
    assert [observation.source_metadata for observation in observations] == [
        {"source_record_index": index} for index in range(4)
    ]
    assert observations[0].source_content_hash == compute_source_content_hash(
        decoded["jobs"][0]
    )
    assert observations[3].source_content_hash == compute_source_content_hash(
        decoded["jobs"][3]
    )
    assert set(record.observation_id for record in result.valid_records) == set(
        observation.id for observation in observations
    )
    assert await count_rows(database_context, Job) == 0
    assert await count_rows(database_context, JobVersion) == 0
    assert await count_rows(database_context, QuarantineRecord) == 0
    assert pipeline_run.status == PipelineRunStatus.RUNNING.value
    assert pipeline_run.records_fetched == 0
    assert pipeline_run.records_valid == 0
    assert pipeline_run.records_quarantined == 0


@pytest.mark.asyncio
async def test_invalid_record_is_returned_while_valid_records_are_persisted(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_invalid_record.json"),
    )

    result = await create_service(
        database_context,
        setup.storage,
    ).process_raw_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    observations = await load_observations(
        database_context.session_factory,
        setup.raw_snapshot.id,
    )
    snapshot = await load_snapshot(
        database_context.session_factory,
        setup.raw_snapshot.id,
    )

    assert result.records_fetched == 3
    assert result.records_valid == 2
    assert result.records_invalid == 1
    assert [observation.external_job_id for observation in observations] == [
        "2001",
        "2003",
    ]
    assert [observation.raw_record_locator for observation in observations] == [
        "jobs[0]",
        "jobs[2]",
    ]
    invalid = result.invalid_records[0]
    assert invalid.source_record_index == 1
    assert invalid.raw_record_locator == "jobs[1]"
    assert invalid.external_job_id is None
    assert invalid.error_category == RECORD_VALIDATION_FAILED
    assert invalid.error_code == "GREENHOUSE_RECORD_INVALID"
    assert snapshot.record_count == 3
    assert await count_rows(database_context, QuarantineRecord) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_bytes",
    [
        fixture_bytes("jobs_invalid_top_level.json"),
        b'{"jobs":',
        b"\xff",
        b"42",
    ],
    ids=["invalid-top-level", "invalid-json", "invalid-utf8", "json-scalar"],
)
async def test_source_level_validation_failure_writes_nothing(
    database_context: DatabaseContext,
    tmp_path: Path,
    raw_bytes: bytes,
) -> None:
    setup = await create_snapshot_setup(database_context, tmp_path, raw_bytes)

    with pytest.raises(GreenhouseResponseShapeError):
        await create_service(
            database_context,
            setup.storage,
        ).process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    assert (
        await load_observations(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
        == []
    )
    assert (
        await load_snapshot(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
    ).record_count is None


@pytest.mark.asyncio
async def test_empty_board_is_successfully_marked_processed(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        b'{"jobs": [], "meta": {"total": 0}}',
    )
    service = create_service(database_context, setup.storage)

    result = await service.process_raw_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )

    assert result.records_fetched == 0
    assert result.records_valid == 0
    assert result.records_invalid == 0
    assert result.valid_records == ()
    assert result.invalid_records == ()
    assert (
        await load_snapshot(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
    ).record_count == 0
    assert (
        await load_observations(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
        == []
    )

    with pytest.raises(RawSnapshotAlreadyProcessedError):
        await service.process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )


@pytest.mark.asyncio
async def test_duplicate_external_id_keeps_first_and_reports_later_record(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    raw_bytes = json.dumps(
        {
            "jobs": [
                {
                    "id": 1001,
                    "title": "First",
                    "absolute_url": "https://example.com/jobs/1001",
                },
                {
                    "id": 1001,
                    "title": "Duplicate",
                    "absolute_url": "https://example.com/jobs/1001-copy",
                },
            ]
        }
    ).encode()
    setup = await create_snapshot_setup(database_context, tmp_path, raw_bytes)

    result = await create_service(
        database_context,
        setup.storage,
    ).process_raw_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    observations = await load_observations(
        database_context.session_factory,
        setup.raw_snapshot.id,
    )

    assert result.records_fetched == 2
    assert result.records_valid == 1
    assert result.records_invalid == 1
    assert len(observations) == 1
    assert observations[0].external_job_id == "1001"
    assert observations[0].raw_record_locator == "jobs[0]"
    duplicate = result.invalid_records[0]
    assert duplicate.raw_record_locator == "jobs[1]"
    assert duplicate.external_job_id == "1001"
    assert duplicate.error_category == DUPLICATE_SOURCE_IDENTIFIER
    assert duplicate.error_details["first_occurrence_locator"] == "jobs[0]"


@pytest.mark.asyncio
async def test_integrity_hash_failure_prevents_processing(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_v1.json"),
        content_hash="0" * 64,
    )

    with pytest.raises(RawSnapshotIntegrityError) as exc_info:
        await create_service(
            database_context,
            setup.storage,
        ).process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    assert exc_info.value.code == "RAW_SNAPSHOT_INTEGRITY_FAILED"
    assert (
        await load_observations(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
        == []
    )
    assert (
        await load_snapshot(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
    ).record_count is None


@pytest.mark.asyncio
async def test_integrity_size_failure_prevents_processing(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    raw_bytes = fixture_bytes("jobs_v1.json")
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        raw_bytes,
        content_length_bytes=len(raw_bytes) + 1,
    )

    with pytest.raises(RawSnapshotIntegrityError, match="byte length"):
        await create_service(
            database_context,
            setup.storage,
        ).process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )


@pytest.mark.asyncio
async def test_missing_stored_object_propagates_storage_error(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_v1.json"),
        store_object=False,
    )

    with pytest.raises(ObjectNotFoundError):
        await create_service(
            database_context,
            setup.storage,
        ).process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    assert (
        await load_observations(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
        == []
    )


@pytest.mark.asyncio
async def test_snapshot_pipeline_mismatch_rejects_before_storage_read(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_v1.json"),
    )

    with pytest.raises(RawSnapshotPipelineMismatchError):
        await create_service(
            database_context,
            setup.storage,
        ).process_raw_snapshot(
            pipeline_run_id=uuid4(),
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    assert setup.storage.read_keys == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "provider", "expected_error"),
    [
        (
            PipelineRunStatus.COMPLETED,
            SourceProvider.GREENHOUSE.value,
            PipelineRunNotRunningError,
        ),
        (
            PipelineRunStatus.RUNNING,
            "lever",
            UnsupportedSourceProviderError,
        ),
    ],
)
async def test_invalid_context_rejects_before_storage_read(
    database_context: DatabaseContext,
    tmp_path: Path,
    status: PipelineRunStatus,
    provider: str,
    expected_error: type[Exception],
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_v1.json"),
        status=status,
        provider=provider,
    )

    with pytest.raises(expected_error):
        await create_service(
            database_context,
            setup.storage,
        ).process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    assert setup.storage.read_keys == []


@pytest.mark.asyncio
async def test_missing_snapshot_rejects_before_storage_read(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    storage = RecordingObjectStorage(FilesystemObjectStorage(tmp_path))

    with pytest.raises(RawSnapshotNotFoundError):
        await create_service(database_context, storage).process_raw_snapshot(
            pipeline_run_id=uuid4(),
            raw_snapshot_id=uuid4(),
        )

    assert storage.read_keys == []


@pytest.mark.asyncio
async def test_reprocessing_is_rejected_without_second_storage_read(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_v1.json"),
    )
    service = create_service(database_context, setup.storage)
    await service.process_raw_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    first_read_count = len(setup.storage.read_keys)

    with pytest.raises(RawSnapshotAlreadyProcessedError) as exc_info:
        await service.process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    assert exc_info.value.code == "RAW_SNAPSHOT_ALREADY_PROCESSED"
    assert len(setup.storage.read_keys) == first_read_count


@pytest.mark.asyncio
async def test_database_failure_rolls_back_observations_and_record_count(
    database_context: DatabaseContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_v1.json"),
    )
    original_persist = SourceObservationRepository.persist_processing_result

    async def persist_then_fail(
        repository: SourceObservationRepository,
        *,
        raw_snapshot: RawSnapshot,
        record_count: int,
        observations: list[SourceObservation],
    ) -> None:
        await original_persist(
            repository,
            raw_snapshot=raw_snapshot,
            record_count=record_count,
            observations=observations,
        )
        raise SQLAlchemyError("simulated failure after observation flush")

    monkeypatch.setattr(
        SourceObservationRepository,
        "persist_processing_result",
        persist_then_fail,
    )

    with pytest.raises(SQLAlchemyError, match="simulated failure"):
        await create_service(
            database_context,
            setup.storage,
        ).process_raw_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    assert (
        await load_observations(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
        == []
    )
    assert (
        await load_snapshot(
            database_context.session_factory,
            setup.raw_snapshot.id,
        )
    ).record_count is None
