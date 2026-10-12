import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, update

from app.ingestion.orchestration import SnapshotIngestionOrchestrator
from app.jobs.lifecycle_errors import (
    PresenceDataInvariantError,
    PresenceReconciliationNotAllowedError,
)
from app.jobs.presence import PresenceRun, PresenceUnsafeReason
from app.jobs.presence_service import PresenceSetBuilder
from app.jobs.schemas import CanonicalJobInput
from app.pipeline_runs.errors import PipelineRunNotFoundError
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.quarantine.models import QuarantineRecord, QuarantineStatus
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.storage.filesystem import FilesystemObjectStorage
from tests.database_counts import capture_table_counts
from tests.integration.ingestion.test_snapshot_ingestion_orchestration import (
    payload_for_ids,
)
from tests.integration.lifecycle.helpers import (
    RETRIEVED_AT,
    build_presence,
    create_presence_run,
)
from tests.test_changed_job_persistence import DatabaseContext, create_source


@pytest.mark.asyncio
async def test_observations_only_preserves_identity_counts_and_all_tables(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]"), ("1002", "jobs[1]"), ("1003", "jobs[2]")],
    )
    before = await capture_table_counts(database_context.connection)

    result = await build_presence(database_context, setup.run.id)

    assert result.pipeline_run_id == setup.run.id
    assert result.source_connection_id == setup.source.id
    assert result.present_external_job_ids == frozenset({"1001", "1002", "1003"})
    assert result.observed_external_job_ids == result.present_external_job_ids
    assert result.records_fetched == result.observed_record_count == 3
    assert result.quarantined_record_count == 0
    assert result.presence_reconciliation_safe is True
    assert await capture_table_counts(database_context.connection) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("quarantine_id", ["1003", None, "", "  "])
async def test_partial_success_safety_depends_on_quarantine_identity(
    database_context: DatabaseContext,
    quarantine_id: str | None,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]"), ("1002", "jobs[1]")],
        quarantines=[(quarantine_id, "jobs[2]")],
    )

    result = await build_presence(database_context, setup.run.id)

    assert setup.run.status == PipelineRunStatus.COMPLETED_WITH_ERRORS.value
    assert result.observed_external_job_ids == frozenset({"1001", "1002"})
    assert result.quarantined_record_count == 1
    if quarantine_id == "1003":
        assert result.present_external_job_ids == frozenset({"1001", "1002", "1003"})
        assert result.presence_reconciliation_safe is True
        assert result.recoverable_quarantine_count == 1
        assert result.unsafe_reason is None
    else:
        assert result.present_external_job_ids == frozenset({"1001", "1002"})
        assert result.presence_reconciliation_safe is False
        assert result.unidentified_quarantine_count == 1
        assert (
            result.unsafe_reason is PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS
        )


@pytest.mark.asyncio
async def test_mapping_failure_overlap_is_presence_only(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]"), ("1002", "jobs[1]")],
        quarantines=[("1001", "jobs[0]")],
        records_valid=1,
    )

    result = await build_presence(database_context, setup.run.id)

    assert result.records_fetched == 2
    assert result.observed_record_count == 2
    assert result.observed_external_job_ids == frozenset({"1002"})
    assert result.recoverable_quarantine_external_job_ids == frozenset({"1001"})
    assert result.present_external_job_ids == frozenset({"1001", "1002"})
    assert result.presence_reconciliation_safe is True


@pytest.mark.asyncio
async def test_quarantined_duplicate_at_another_locator_preserves_valid_evidence(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        quarantines=[("1001", "jobs[1]")],
    )

    result = await build_presence(database_context, setup.run.id)

    assert result.present_external_job_ids == frozenset({"1001"})
    assert result.observed_external_job_ids == frozenset({"1001"})
    assert result.recoverable_quarantine_external_job_ids == frozenset({"1001"})
    assert result.records_fetched == 2
    assert result.presence_reconciliation_safe is True


@pytest.mark.asyncio
async def test_successful_empty_board_is_safe(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(database_context)

    result = await build_presence(database_context, setup.run.id)

    assert result.present_external_job_ids == frozenset()
    assert result.presence_reconciliation_safe is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [PipelineRunStatus.FAILED, PipelineRunStatus.PENDING, PipelineRunStatus.RUNNING],
)
async def test_non_successful_run_is_rejected(
    database_context: DatabaseContext,
    status: PipelineRunStatus,
) -> None:
    setup = await create_presence_run(database_context, status=status)

    with pytest.raises(PresenceReconciliationNotAllowedError):
        await build_presence(database_context, setup.run.id)


@pytest.mark.asyncio
async def test_missing_run_uses_stable_error(database_context: DatabaseContext) -> None:
    with pytest.raises(PipelineRunNotFoundError):
        await build_presence(database_context, uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metrics",
    [
        {"records_fetched": 9},
        {"records_fetched": 4, "records_valid": 3},
        {"records_fetched": 4, "records_quarantined": 2},
    ],
)
async def test_metric_and_persisted_count_mismatches_are_invariant_errors(
    database_context: DatabaseContext,
    metrics: dict[str, int],
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]"), ("1002", "jobs[1]")],
        quarantines=[("1003", "jobs[2]")],
    )
    async with database_context.session_factory.begin() as session:
        await session.execute(
            update(PipelineRun).where(PipelineRun.id == setup.run.id).values(**metrics)
        )

    with pytest.raises(PresenceDataInvariantError):
        await build_presence(database_context, setup.run.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["observation", "quarantine"])
async def test_processing_rows_cannot_belong_to_another_source(
    database_context: DatabaseContext,
    record_type: str,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        quarantines=[("1002", "jobs[1]")],
    )
    other_source = await create_source(database_context.session_factory)
    model = SourceObservation if record_type == "observation" else QuarantineRecord
    row_id = (
        setup.observations[0].id
        if record_type == "observation"
        else setup.quarantines[0].id
    )
    async with database_context.session_factory.begin() as session:
        await session.execute(
            update(model)
            .where(model.id == row_id)
            .values(source_connection_id=other_source.id)
        )

    with pytest.raises(PresenceDataInvariantError, match="another source"):
        await build_presence(database_context, setup.run.id)


@pytest.mark.asyncio
async def test_observation_cannot_reference_another_runs_snapshot(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context, observations=[("1001", "jobs[0]")]
    )
    other_run = await create_presence_run(database_context, source=setup.source)
    async with database_context.session_factory.begin() as session:
        await session.execute(
            update(SourceObservation)
            .where(SourceObservation.id == setup.observations[0].id)
            .values(raw_snapshot_id=other_run.snapshot.id)
        )

    with pytest.raises(PresenceDataInvariantError, match="another run's snapshot"):
        await build_presence(database_context, setup.run.id)


@pytest.mark.asyncio
async def test_resolving_quarantine_does_not_reclassify_historical_evidence(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        quarantines=[("1001", "jobs[0]")],
        records_valid=0,
    )
    async with database_context.session_factory.begin() as session:
        await session.execute(
            update(QuarantineRecord)
            .where(QuarantineRecord.id == setup.quarantines[0].id)
            .values(status=QuarantineStatus.RESOLVED.value, resolved_at=RETRIEVED_AT)
        )

    result = await build_presence(database_context, setup.run.id)

    assert result.observed_external_job_ids == frozenset()
    assert result.present_external_job_ids == frozenset({"1001"})
    assert result.quarantined_record_count == result.recoverable_quarantine_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot_state", ["missing", "unprocessed", "wrong_count"])
async def test_completed_run_requires_verified_snapshot_record_count(
    database_context: DatabaseContext,
    snapshot_state: str,
) -> None:
    setup = await create_presence_run(database_context)
    async with database_context.session_factory.begin() as session:
        if snapshot_state == "missing":
            await session.execute(
                delete(RawSnapshot).where(RawSnapshot.id == setup.snapshot.id)
            )
        else:
            await session.execute(
                update(RawSnapshot)
                .where(RawSnapshot.id == setup.snapshot.id)
                .values(record_count=None if snapshot_state == "unprocessed" else 1)
            )

    with pytest.raises(PresenceDataInvariantError, match="snapshot record count"):
        await build_presence(database_context, setup.run.id)


@pytest.mark.asyncio
async def test_real_phase_one_mapper_failure_builds_safe_presence_only_evidence(
    database_context: DatabaseContext,
    tmp_path: Path,
) -> None:
    setup = await create_presence_run(
        database_context, status=PipelineRunStatus.RUNNING
    )
    raw_bytes = payload_for_ids("jobs_v1.json", [1001, 1002])
    storage = FilesystemObjectStorage(tmp_path)
    await storage.put_bytes(
        key=setup.snapshot.r2_object_key,
        data=raw_bytes,
        content_type="application/json",
    )
    async with database_context.session_factory.begin() as session:
        await session.execute(
            update(RawSnapshot)
            .where(RawSnapshot.id == setup.snapshot.id)
            .values(
                record_count=None,
                content_hash=hashlib.sha256(raw_bytes).hexdigest(),
                content_length_bytes=len(raw_bytes),
            )
        )

    def fail_first_mapping(source_record: GreenhouseJob) -> CanonicalJobInput:
        if source_record.id == 1001:
            raise ValueError("fixture mapper failure")
        return map_greenhouse_job(source_record)

    processed = await SnapshotIngestionOrchestrator(
        database_context.session_factory,
        object_storage=storage,
        mapper=fail_first_mapping,
    ).process_snapshot(pipeline_run_id=setup.run.id, raw_snapshot_id=setup.snapshot.id)
    result = await build_presence(database_context, setup.run.id)

    assert processed.records_fetched == 2
    assert processed.records_valid == processed.records_quarantined == 1
    assert result.observed_record_count == 2
    assert result.observed_external_job_ids == frozenset({"1002"})
    assert result.recoverable_quarantine_external_job_ids == frozenset({"1001"})
    assert result.presence_reconciliation_safe is True


@pytest.mark.asyncio
async def test_running_run_requires_internal_processed_handoff_and_checks_durable_counts(
    database_context: DatabaseContext,
) -> None:
    setup = await create_presence_run(
        database_context,
        observations=[("1001", "jobs[0]")],
        status=PipelineRunStatus.RUNNING,
    )
    async with database_context.session_factory.begin() as session:
        await session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == setup.run.id)
            .values(records_fetched=0, records_valid=0, jobs_new=0)
        )
    handoff = PresenceRun(setup.run.id, setup.source.id, "completed", 1, 1, 0)
    async with database_context.session_factory() as session:
        builder = PresenceSetBuilder(session)
        with pytest.raises(PresenceReconciliationNotAllowedError):
            await builder.build_presence_set(setup.run.id)
        result = await builder.build_presence_set(setup.run.id, processed_run=handoff)
        assert result.present_external_job_ids == {"1001"}
        assert result.presence_reconciliation_safe
        with pytest.raises(PresenceDataInvariantError, match="snapshot record count"):
            await builder.build_presence_set(
                setup.run.id, processed_run=replace(handoff, records_fetched=2)
            )
        for wrong in (
            replace(handoff, pipeline_run_id=uuid4()),
            replace(handoff, source_connection_id=uuid4()),
        ):
            with pytest.raises(PresenceDataInvariantError, match="handoff"):
                await builder.build_presence_set(setup.run.id, processed_run=wrong)
        run = await session.get(PipelineRun, setup.run.id)
        assert run is not None
        assert run.status == "running" and run.completed_at is None
        assert run.records_fetched == run.records_valid == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [PipelineRunStatus.PENDING, PipelineRunStatus.FAILED, PipelineRunStatus.COMPLETED],
)
async def test_processed_handoff_cannot_override_non_running_state(
    database_context: DatabaseContext, status: PipelineRunStatus
) -> None:
    setup = await create_presence_run(database_context, status=status)
    handoff = PresenceRun(setup.run.id, setup.source.id, "completed", 0, 0, 0)
    async with database_context.session_factory() as session:
        with pytest.raises(PresenceReconciliationNotAllowedError):
            await PresenceSetBuilder(session).build_presence_set(
                setup.run.id, processed_run=handoff
            )
