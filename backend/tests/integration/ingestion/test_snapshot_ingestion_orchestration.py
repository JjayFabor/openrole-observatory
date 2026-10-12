import hashlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
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
from app.ingestion.errors import PipelineMetricsInvariantError
from app.ingestion.orchestration import (
    DATABASE_WRITE_FAILED,
    PIPELINE_INTERNAL_ERROR,
    RAW_STORAGE_FAILED,
    SOURCE_RESPONSE_INVALID,
    SnapshotIngestionOrchestrator,
    validate_pipeline_metrics,
)
from app.jobs.errors import NewJobDatabaseError
from app.jobs.models import Job, JobVersion
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
    NewJobPersistenceService,
    PersistNewJobCommand,
)
from app.pipeline_runs.errors import PipelineRunAlreadyFinalizedError
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.pipeline_runs.schemas import PipelineMetrics
from app.pipeline_runs.service import PipelineRunService
from app.quarantine.models import QuarantineRecord, QuarantineStatus
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.source_observations.source_records import compute_source_content_hash
from app.sources.greenhouse.errors import GreenhouseResponseShapeError
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.sources.greenhouse.validation import parse_greenhouse_response
from app.sources.models import SourceConnection, SourceProvider
from app.storage.errors import ObjectNotFoundError
from app.storage.filesystem import FilesystemObjectStorage
from tests.database_counts import (
    TableCounts,
    capture_table_counts,
    count_rows_since_baseline,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "greenhouse"
PREVIOUS_OBSERVED_AT = datetime(2026, 10, 5, 9, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 10, 10, 9, tzinfo=UTC)
FINALIZED_AT = datetime(2026, 10, 10, 10, tzinfo=UTC)
EARLIER_SUCCESS_AT = datetime(2026, 10, 1, 9, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]
    baseline_counts: TableCounts


@dataclass(frozen=True, slots=True)
class SnapshotSetup:
    source: SourceConnection
    pipeline_run: PipelineRun
    raw_snapshot: RawSnapshot
    storage: FilesystemObjectStorage


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


def fixture_document(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURE_ROOT / name).read_bytes())
    assert isinstance(value, dict)
    return value


def fixture_bytes(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def payload_for_ids(name: str, external_ids: list[int]) -> bytes:
    document = fixture_document(name)
    jobs = document["jobs"]
    assert isinstance(jobs, list)
    selected = [job for job in jobs if job["id"] in external_ids]
    return json.dumps({"jobs": selected, "meta": {"total": len(selected)}}).encode()


def valid_and_invalid_payload() -> bytes:
    valid_jobs = fixture_document("jobs_v1.json")["jobs"]
    invalid_jobs = fixture_document("jobs_invalid_record.json")["jobs"]
    assert isinstance(valid_jobs, list)
    assert isinstance(invalid_jobs, list)
    jobs = [*valid_jobs, invalid_jobs[1]]
    return json.dumps({"jobs": jobs, "meta": {"total": len(jobs)}}).encode()


async def create_snapshot_setup(
    database_context: DatabaseContext,
    storage_root: Path,
    raw_bytes: bytes,
    *,
    status: PipelineRunStatus = PipelineRunStatus.RUNNING,
    store_object: bool = True,
    last_successful_sync_at: datetime | None = None,
) -> SnapshotSetup:
    suffix = uuid4().hex
    storage = FilesystemObjectStorage(storage_root)
    object_key = f"bronze/tests/{suffix}/jobs.json"
    if store_object:
        await storage.put_bytes(
            key=object_key,
            data=raw_bytes,
            content_type="application/json",
        )

    async with database_context.session_factory.begin() as session:
        source = SourceConnection(
            company=Company(name=f"Company {suffix}", slug=f"company-{suffix}"),
            provider=SourceProvider.GREENHOUSE.value,
            external_account_key=f"board-{suffix}",
            last_successful_sync_at=last_successful_sync_at,
        )
        pipeline_run = PipelineRun(
            source_connection=source,
            status=status.value,
            started_at=RETRIEVED_AT,
            completed_at=FINALIZED_AT if status in _terminal_statuses() else None,
        )
        raw_snapshot = RawSnapshot(
            pipeline_run=pipeline_run,
            r2_object_key=object_key,
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
            content_type="application/json",
            content_length_bytes=len(raw_bytes),
            record_count=None,
            retrieved_at=RETRIEVED_AT,
        )
        session.add(raw_snapshot)
        await session.flush()

    return SnapshotSetup(source, pipeline_run, raw_snapshot, storage)


def _terminal_statuses() -> set[PipelineRunStatus]:
    return {
        PipelineRunStatus.COMPLETED,
        PipelineRunStatus.COMPLETED_WITH_ERRORS,
        PipelineRunStatus.FAILED,
    }


def create_orchestrator(
    database_context: DatabaseContext,
    setup: SnapshotSetup,
    *,
    mapper: Callable[[GreenhouseJob], CanonicalJobInput] = map_greenhouse_job,
) -> SnapshotIngestionOrchestrator:
    lifecycle = PipelineRunService(
        database_context.session_factory,
        clock=lambda: FINALIZED_AT,
    )
    return SnapshotIngestionOrchestrator(
        database_context.session_factory,
        object_storage=setup.storage,
        mapper=mapper,
        pipeline_run_service=lifecycle,
    )


async def preload_jobs(
    database_context: DatabaseContext,
    source_connection_id: UUID,
    raw_bytes: bytes,
) -> None:
    validation = parse_greenhouse_response(raw_bytes)
    assert validation.invalid_records == ()
    suffix = uuid4().hex

    async with database_context.session_factory.begin() as session:
        run = PipelineRun(
            source_connection_id=source_connection_id,
            status=PipelineRunStatus.COMPLETED.value,
            started_at=PREVIOUS_OBSERVED_AT,
            completed_at=PREVIOUS_OBSERVED_AT,
            records_fetched=len(validation.validated_records),
            records_valid=len(validation.validated_records),
            jobs_new=len(validation.validated_records),
        )
        snapshot = RawSnapshot(
            pipeline_run=run,
            r2_object_key=f"bronze/tests/preload-{suffix}/jobs.json",
            content_hash="a" * 64,
            content_type="application/json",
            content_length_bytes=len(raw_bytes),
            record_count=len(validation.validated_records),
            retrieved_at=PREVIOUS_OBSERVED_AT,
        )
        observations = [
            SourceObservation(
                pipeline_run=run,
                source_connection_id=source_connection_id,
                raw_snapshot=snapshot,
                external_job_id=str(record.source_record.id),
                raw_record_locator=f"jobs[{record.index}]",
                source_content_hash=compute_source_content_hash(record.raw_record),
                observed_at=PREVIOUS_OBSERVED_AT,
                source_metadata={"source_record_index": record.index},
            )
            for record in validation.validated_records
        ]
        session.add_all(observations)
        await session.flush()

    service = NewJobPersistenceService(database_context.session_factory)
    for observation, source_record in zip(
        observations,
        validation.valid_records,
        strict=True,
    ):
        await service.create_new_job(
            PersistNewJobCommand(observation.id, source_record)
        )


async def load_run(database_context: DatabaseContext, run_id: UUID) -> PipelineRun:
    async with database_context.session_factory() as session:
        run = await session.get(PipelineRun, run_id)
    assert run is not None
    return run


async def load_source(
    database_context: DatabaseContext,
    source_id: UUID,
) -> SourceConnection:
    async with database_context.session_factory() as session:
        source = await session.get(SourceConnection, source_id)
    assert source is not None
    return source


async def load_quarantines(
    database_context: DatabaseContext,
    run_id: UUID,
) -> list[QuarantineRecord]:
    async with database_context.session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(QuarantineRecord)
                    .where(QuarantineRecord.pipeline_run_id == run_id)
                    .order_by(QuarantineRecord.raw_record_locator)
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


def assert_run_metrics(run: PipelineRun, expected: PipelineMetrics) -> None:
    assert (
        PipelineMetrics(
            records_fetched=run.records_fetched,
            records_valid=run.records_valid,
            records_quarantined=run.records_quarantined,
            jobs_new=run.jobs_new,
            jobs_changed=run.jobs_changed,
            jobs_unchanged=run.jobs_unchanged,
        )
        == expected
    )


@pytest.mark.asyncio
async def test_all_new_records_complete_with_exact_metrics(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        payload_for_ids("jobs_v1.json", [1001, 1002, 1003]),
    )

    result = await create_orchestrator(database_context, setup).process_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    stored_run = await load_run(database_context, setup.pipeline_run.id)
    stored_source = await load_source(database_context, setup.source.id)
    expected = PipelineMetrics(records_fetched=3, records_valid=3, jobs_new=3)

    assert result.status is PipelineRunStatus.COMPLETED
    assert result.records_fetched == 3
    assert result.records_valid == 3
    assert result.records_quarantined == 0
    assert result.jobs_new == 3
    assert result.jobs_changed == 0
    assert result.jobs_unchanged == 0
    assert_run_metrics(stored_run, expected)
    assert stored_run.status == PipelineRunStatus.COMPLETED.value
    assert stored_source.last_successful_sync_at == FINALIZED_AT
    assert await count_rows(database_context, Job) == 3
    assert await count_rows(database_context, JobVersion) == 3
    assert await count_rows(database_context, SourceObservation) == 3
    assert await count_rows(database_context, QuarantineRecord) == 0


@pytest.mark.asyncio
async def test_all_unchanged_records_do_not_create_versions(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    raw_bytes = payload_for_ids("jobs_v1.json", [1001, 1002, 1003])
    setup = await create_snapshot_setup(database_context, tmp_path, raw_bytes)
    await preload_jobs(database_context, setup.source.id, raw_bytes)

    result = await create_orchestrator(database_context, setup).process_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    stored_run = await load_run(database_context, setup.pipeline_run.id)

    assert result.status is PipelineRunStatus.COMPLETED
    assert_run_metrics(
        stored_run,
        PipelineMetrics(records_fetched=3, records_valid=3, jobs_unchanged=3),
    )
    assert await count_rows(database_context, Job) == 3
    assert await count_rows(database_context, JobVersion) == 3
    assert await count_rows(database_context, SourceObservation) == 6


@pytest.mark.asyncio
async def test_mixed_records_route_to_new_unchanged_and_changed(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    incoming = payload_for_ids("jobs_v2.json", [1004, 1003, 1001])
    setup = await create_snapshot_setup(database_context, tmp_path, incoming)
    await preload_jobs(
        database_context,
        setup.source.id,
        payload_for_ids("jobs_v1.json", [1003, 1001]),
    )

    result = await create_orchestrator(database_context, setup).process_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    stored_run = await load_run(database_context, setup.pipeline_run.id)

    assert result.status is PipelineRunStatus.COMPLETED
    assert_run_metrics(
        stored_run,
        PipelineMetrics(
            records_fetched=3,
            records_valid=3,
            jobs_new=1,
            jobs_changed=1,
            jobs_unchanged=1,
        ),
    )
    assert await count_rows(database_context, Job) == 3
    assert await count_rows(database_context, JobVersion) == 4
    assert await count_rows(database_context, SourceObservation) == 5
    assert await count_rows(database_context, QuarantineRecord) == 0


@pytest.mark.asyncio
async def test_invalid_record_is_quarantined_with_lineage_and_run_partially_succeeds(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        valid_and_invalid_payload(),
    )

    result = await create_orchestrator(database_context, setup).process_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    stored_run = await load_run(database_context, setup.pipeline_run.id)
    stored_source = await load_source(database_context, setup.source.id)
    quarantines = await load_quarantines(database_context, setup.pipeline_run.id)

    assert result.status is PipelineRunStatus.COMPLETED_WITH_ERRORS
    assert_run_metrics(
        stored_run,
        PipelineMetrics(
            records_fetched=5,
            records_valid=4,
            records_quarantined=1,
            jobs_new=4,
        ),
    )
    assert stored_source.last_successful_sync_at == FINALIZED_AT
    assert len(quarantines) == 1
    quarantine = quarantines[0]
    assert quarantine.pipeline_run_id == setup.pipeline_run.id
    assert quarantine.source_connection_id == setup.source.id
    assert quarantine.raw_snapshot_id == setup.raw_snapshot.id
    assert quarantine.raw_record_locator == "jobs[4]"
    assert quarantine.error_category == "record_validation_failed"
    assert quarantine.status == QuarantineStatus.OPEN.value
    assert await count_rows(database_context, SourceObservation) == 4
    assert await count_rows(database_context, Job) == 4
    assert await count_rows(database_context, JobVersion) == 4


@pytest.mark.asyncio
async def test_mapping_failure_is_quarantined_and_later_record_continues(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        payload_for_ids("jobs_v1.json", [1001, 1002]),
    )

    def fail_first_mapping(source_record: GreenhouseJob) -> CanonicalJobInput:
        if source_record.id == 1001:
            raise ValueError("intentional mapper failure")
        return map_greenhouse_job(source_record)

    result = await create_orchestrator(
        database_context,
        setup,
        mapper=fail_first_mapping,
    ).process_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    stored_run = await load_run(database_context, setup.pipeline_run.id)
    quarantines = await load_quarantines(database_context, setup.pipeline_run.id)

    assert result.status is PipelineRunStatus.COMPLETED_WITH_ERRORS
    assert_run_metrics(
        stored_run,
        PipelineMetrics(
            records_fetched=2,
            records_valid=1,
            records_quarantined=1,
            jobs_new=1,
        ),
    )
    assert len(quarantines) == 1
    assert quarantines[0].external_job_id == "1001"
    assert quarantines[0].raw_record_locator == "jobs[0]"
    assert quarantines[0].error_category == "normalization_failed"
    assert await count_rows(database_context, SourceObservation) == 2
    assert await count_rows(database_context, Job) == 1


@pytest.mark.asyncio
async def test_unexpected_record_error_fails_run_without_quarantine(
    database_context: DatabaseContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        payload_for_ids("jobs_v1.json", [1001, 1002]),
        last_successful_sync_at=EARLIER_SUCCESS_AT,
    )

    async def fail_unexpectedly(
        _service: NewJobPersistenceService,
        _command: PersistNewJobCommand,
    ) -> None:
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(
        NewJobPersistenceService,
        "create_new_job",
        fail_unexpectedly,
    )

    with pytest.raises(RuntimeError, match="sensitive internal detail"):
        await create_orchestrator(database_context, setup).process_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    stored_run = await load_run(database_context, setup.pipeline_run.id)
    stored_source = await load_source(database_context, setup.source.id)
    assert stored_run.status == PipelineRunStatus.FAILED.value
    assert stored_run.error_code == PIPELINE_INTERNAL_ERROR
    assert "sensitive internal detail" not in (stored_run.error_summary or "")
    assert stored_source.last_successful_sync_at == EARLIER_SUCCESS_AT
    assert_run_metrics(stored_run, PipelineMetrics(records_fetched=2))
    assert await count_rows(database_context, QuarantineRecord) == 0
    assert await count_rows(database_context, SourceObservation) == 2


@pytest.mark.asyncio
async def test_database_record_error_fails_run_without_quarantine(
    database_context: DatabaseContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        payload_for_ids("jobs_v1.json", [1001]),
    )

    async def fail_database_write(
        _service: NewJobPersistenceService,
        command: PersistNewJobCommand,
    ) -> None:
        raise NewJobDatabaseError(command.source_observation_id)

    monkeypatch.setattr(
        NewJobPersistenceService,
        "create_new_job",
        fail_database_write,
    )

    with pytest.raises(NewJobDatabaseError):
        await create_orchestrator(database_context, setup).process_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    stored_run = await load_run(database_context, setup.pipeline_run.id)
    assert stored_run.status == PipelineRunStatus.FAILED.value
    assert stored_run.error_code == DATABASE_WRITE_FAILED
    assert await count_rows(database_context, QuarantineRecord) == 0


@pytest.mark.asyncio
async def test_invalid_top_level_snapshot_fails_without_quarantine(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        fixture_bytes("jobs_invalid_top_level.json"),
    )

    with pytest.raises(GreenhouseResponseShapeError):
        await create_orchestrator(database_context, setup).process_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    stored_run = await load_run(database_context, setup.pipeline_run.id)
    assert stored_run.status == PipelineRunStatus.FAILED.value
    assert stored_run.error_code == SOURCE_RESPONSE_INVALID
    assert await count_rows(database_context, QuarantineRecord) == 0
    assert await count_rows(database_context, SourceObservation) == 0


@pytest.mark.asyncio
async def test_missing_raw_object_fails_pipeline(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        payload_for_ids("jobs_v1.json", [1001]),
        store_object=False,
    )

    with pytest.raises(ObjectNotFoundError):
        await create_orchestrator(database_context, setup).process_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    stored_run = await load_run(database_context, setup.pipeline_run.id)
    assert stored_run.status == PipelineRunStatus.FAILED.value
    assert stored_run.error_code == RAW_STORAGE_FAILED
    assert await count_rows(database_context, QuarantineRecord) == 0


@pytest.mark.asyncio
async def test_empty_snapshot_completes_with_zero_metrics(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    raw_bytes = b'{"jobs": [], "meta": {"total": 0}}'
    setup = await create_snapshot_setup(database_context, tmp_path, raw_bytes)

    result = await create_orchestrator(database_context, setup).process_snapshot(
        pipeline_run_id=setup.pipeline_run.id,
        raw_snapshot_id=setup.raw_snapshot.id,
    )
    stored_run = await load_run(database_context, setup.pipeline_run.id)

    assert result.status is PipelineRunStatus.COMPLETED
    assert_run_metrics(stored_run, PipelineMetrics())
    assert await count_rows(database_context, SourceObservation) == 0
    assert await count_rows(database_context, Job) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_status",
    [PipelineRunStatus.COMPLETED, PipelineRunStatus.FAILED],
)
async def test_finalized_run_is_rejected_before_source_processing(
    database_context: DatabaseContext,
    tmp_path: Path,
    terminal_status: PipelineRunStatus,
) -> None:
    setup = await create_snapshot_setup(
        database_context,
        tmp_path,
        payload_for_ids("jobs_v1.json", [1001]),
        status=terminal_status,
    )

    with pytest.raises(PipelineRunAlreadyFinalizedError):
        await create_orchestrator(database_context, setup).process_snapshot(
            pipeline_run_id=setup.pipeline_run.id,
            raw_snapshot_id=setup.raw_snapshot.id,
        )

    async with database_context.session_factory() as session:
        snapshot = await session.get(RawSnapshot, setup.raw_snapshot.id)
    assert snapshot is not None
    assert snapshot.record_count is None
    assert await count_rows(database_context, SourceObservation) == 0
    assert await count_rows(database_context, QuarantineRecord) == 0


@pytest.mark.parametrize(
    "metrics",
    [
        PipelineMetrics(
            records_fetched=10,
            records_valid=8,
            records_quarantined=1,
            jobs_new=8,
        ),
        PipelineMetrics(
            records_fetched=10,
            records_valid=9,
            records_quarantined=1,
            jobs_new=8,
        ),
    ],
)
def test_pipeline_metrics_invariants_reject_inconsistent_counts(
    metrics: PipelineMetrics,
) -> None:
    with pytest.raises(PipelineMetricsInvariantError):
        validate_pipeline_metrics(metrics)


def test_pipeline_failure_taxonomy_constants_are_stable() -> None:
    assert {
        SOURCE_RESPONSE_INVALID,
        RAW_STORAGE_FAILED,
        DATABASE_WRITE_FAILED,
        PIPELINE_INTERNAL_ERROR,
    } == {
        "SOURCE_RESPONSE_INVALID",
        "RAW_STORAGE_FAILED",
        "DATABASE_WRITE_FAILED",
        "PIPELINE_INTERNAL_ERROR",
    }


@pytest.mark.asyncio
async def test_record_stage_returns_metrics_without_finalizing_run_or_source(
    database_context: DatabaseContext, tmp_path: Path
) -> None:
    setup = await create_snapshot_setup(
        database_context, tmp_path, payload_for_ids("jobs_v1.json", [1001, 1002])
    )
    result = await create_orchestrator(database_context, setup).process_records(
        pipeline_run_id=setup.pipeline_run.id, raw_snapshot_id=setup.raw_snapshot.id
    )
    run = await load_run(database_context, setup.pipeline_run.id)
    source = await load_source(database_context, setup.source.id)
    assert result.metrics == PipelineMetrics(
        records_fetched=2, records_valid=2, jobs_new=2
    )
    assert result.status is PipelineRunStatus.COMPLETED
    assert run.status == "running" and run.completed_at is None
    assert source.last_successful_sync_at is None
    assert await count_rows(database_context, Job) == 2
