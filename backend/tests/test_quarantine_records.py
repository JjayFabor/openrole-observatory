from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.companies.models import Company
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.quarantine.models import QuarantineRecord, QuarantineStatus
from app.raw_snapshots.models import RawSnapshot
from app.sources.models import SourceConnection, SourceProvider

OBSERVED_AT = datetime(2026, 10, 6, 9, tzinfo=UTC)


async def create_source(
    db_session: AsyncSession,
    *,
    key: str = "acme",
) -> tuple[Company, SourceConnection]:
    company = Company(name=f"Company {key}", slug=key)
    source = SourceConnection(
        company=company,
        provider=SourceProvider.GREENHOUSE.value,
        external_account_key=key,
    )
    db_session.add(source)
    await db_session.flush()
    return company, source


async def create_run_and_snapshot(
    db_session: AsyncSession,
    source: SourceConnection,
    *,
    observed_at: datetime = OBSERVED_AT,
    records_fetched: int = 1,
    records_valid: int = 0,
    records_quarantined: int = 1,
) -> tuple[PipelineRun, RawSnapshot]:
    pipeline_run = PipelineRun(
        source_connection=source,
        status=PipelineRunStatus.COMPLETED_WITH_ERRORS.value,
        started_at=observed_at,
        completed_at=observed_at,
        records_fetched=records_fetched,
        records_valid=records_valid,
        records_quarantined=records_quarantined,
    )
    db_session.add(pipeline_run)
    await db_session.flush()
    snapshot = RawSnapshot(
        pipeline_run=pipeline_run,
        r2_object_key=f"bronze/test/run={pipeline_run.id}/jobs.json",
        content_hash="a" * 64,
        content_type="application/json",
        record_count=records_fetched,
        retrieved_at=observed_at,
    )
    db_session.add(snapshot)
    await db_session.flush()
    return pipeline_run, snapshot


def build_quarantine_record(
    source: SourceConnection,
    pipeline_run: PipelineRun,
    snapshot: RawSnapshot,
    *,
    external_job_id: str | None = "1001",
    raw_record_locator: str | None = "jobs[3]",
    error_category: str = "schema_validation_failed",
) -> QuarantineRecord:
    return QuarantineRecord(
        pipeline_run=pipeline_run,
        source_connection=source,
        raw_snapshot=snapshot,
        external_job_id=external_job_id,
        raw_record_locator=raw_record_locator,
        error_category=error_category,
        error_code="GREENHOUSE_UPDATED_AT_INVALID",
        error_message="Greenhouse job field `updated_at` is not a valid timestamp.",
        error_details={
            "field": "updated_at",
            "validation_type": "datetime_parsing",
        },
    )


@pytest.mark.asyncio
async def test_quarantine_record_persists_diagnostics_and_relationships(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    quarantine = build_quarantine_record(source, pipeline_run, snapshot)
    db_session.add(quarantine)
    await db_session.flush()
    quarantine_id = quarantine.id
    run_id = pipeline_run.id
    source_id = source.id
    snapshot_id = snapshot.id
    db_session.expunge_all()

    loaded = (
        await db_session.execute(
            select(QuarantineRecord)
            .options(
                joinedload(QuarantineRecord.pipeline_run),
                joinedload(QuarantineRecord.source_connection),
                joinedload(QuarantineRecord.raw_snapshot),
            )
            .where(QuarantineRecord.id == quarantine_id)
        )
    ).scalar_one()
    loaded_run = (
        await db_session.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.quarantine_records))
            .where(PipelineRun.id == run_id)
        )
    ).scalar_one()
    loaded_source = (
        await db_session.execute(
            select(SourceConnection)
            .options(selectinload(SourceConnection.quarantine_records))
            .where(SourceConnection.id == source_id)
        )
    ).scalar_one()
    loaded_snapshot = (
        await db_session.execute(
            select(RawSnapshot)
            .options(selectinload(RawSnapshot.quarantine_records))
            .where(RawSnapshot.id == snapshot_id)
        )
    ).scalar_one()

    assert loaded.pipeline_run.id == run_id
    assert loaded.source_connection.id == source_id
    assert loaded.raw_snapshot.id == snapshot_id
    assert loaded.external_job_id == "1001"
    assert loaded.raw_record_locator == "jobs[3]"
    assert loaded.error_category == "schema_validation_failed"
    assert loaded.error_code == "GREENHOUSE_UPDATED_AT_INVALID"
    assert "not a valid timestamp" in loaded.error_message
    assert loaded.error_details == {
        "field": "updated_at",
        "validation_type": "datetime_parsing",
    }
    assert loaded.status == QuarantineStatus.OPEN.value
    assert loaded.resolved_at is None
    assert loaded.created_at.tzinfo is not None
    assert [item.id for item in loaded_run.quarantine_records] == [quarantine_id]
    assert [item.id for item in loaded_source.quarantine_records] == [quarantine_id]
    assert [item.id for item in loaded_snapshot.quarantine_records] == [quarantine_id]


@pytest.mark.asyncio
async def test_missing_external_id_and_locator_are_valid_and_details_default_empty(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    quarantine = QuarantineRecord(
        pipeline_run=pipeline_run,
        source_connection=source,
        raw_snapshot=snapshot,
        external_job_id=None,
        raw_record_locator=None,
        error_category="missing_required_identifier",
        error_message="Greenhouse job record is missing field `id`.",
    )
    db_session.add(quarantine)
    await db_session.flush()
    await db_session.refresh(quarantine)

    assert quarantine.external_job_id is None
    assert quarantine.raw_record_locator is None
    assert quarantine.error_code is None
    assert quarantine.error_details == {}
    assert quarantine.status == QuarantineStatus.OPEN.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_parent",
    ["pipeline_run", "source_connection", "raw_snapshot"],
)
async def test_quarantine_foreign_keys_are_enforced(
    db_session: AsyncSession,
    missing_parent: str,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    foreign_keys = {
        "pipeline_run_id": pipeline_run.id,
        "source_connection_id": source.id,
        "raw_snapshot_id": snapshot.id,
    }
    foreign_keys[f"{missing_parent}_id"] = uuid4()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                QuarantineRecord(
                    **foreign_keys,
                    error_category="schema_validation_failed",
                    error_message="Record could not be validated.",
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_one_run_can_contain_multiple_quarantine_records(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(
        db_session,
        source,
        records_fetched=3,
        records_quarantined=3,
    )
    db_session.add_all(
        [
            build_quarantine_record(
                source,
                pipeline_run,
                snapshot,
                external_job_id=str(index),
                raw_record_locator=f"jobs[{index}]",
            )
            for index in range(3)
        ]
    )
    await db_session.flush()

    count = await db_session.scalar(
        select(func.count())
        .select_from(QuarantineRecord)
        .where(QuarantineRecord.pipeline_run_id == pipeline_run.id)
    )

    assert count == 3


@pytest.mark.asyncio
async def test_same_external_id_can_be_quarantined_in_different_runs(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    first_run, first_snapshot = await create_run_and_snapshot(db_session, source)
    second_run, second_snapshot = await create_run_and_snapshot(
        db_session,
        source,
        observed_at=OBSERVED_AT + timedelta(hours=1),
    )
    db_session.add_all(
        [
            build_quarantine_record(source, first_run, first_snapshot),
            build_quarantine_record(source, second_run, second_snapshot),
        ]
    )

    await db_session.flush()


@pytest.mark.asyncio
async def test_resolved_status_requires_a_resolution_timestamp(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    quarantine = build_quarantine_record(source, pipeline_run, snapshot)
    quarantine.status = QuarantineStatus.RESOLVED.value
    quarantine.resolved_at = OBSERVED_AT + timedelta(days=1)
    db_session.add(quarantine)
    await db_session.flush()

    assert quarantine.status == QuarantineStatus.RESOLVED.value
    assert quarantine.resolved_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "resolved_at"),
    [
        (QuarantineStatus.OPEN.value, OBSERVED_AT),
        (QuarantineStatus.RESOLVED.value, None),
        ("ignored", None),
    ],
)
async def test_invalid_status_and_resolution_combinations_are_rejected(
    db_session: AsyncSession,
    status: str,
    resolved_at: datetime | None,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            quarantine = build_quarantine_record(source, pipeline_run, snapshot)
            quarantine.status = status
            quarantine.resolved_at = resolved_at
            db_session.add(quarantine)
            await db_session.flush()


@pytest.mark.asyncio
async def test_partial_success_run_can_preserve_one_malformed_record(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(
        db_session,
        source,
        records_fetched=5,
        records_valid=4,
        records_quarantined=1,
    )
    quarantine = build_quarantine_record(
        source,
        pipeline_run,
        snapshot,
        external_job_id=None,
        raw_record_locator="jobs[4]",
        error_category="missing_required_identifier",
    )
    db_session.add(quarantine)
    await db_session.flush()

    assert pipeline_run.status == PipelineRunStatus.COMPLETED_WITH_ERRORS.value
    assert pipeline_run.records_fetched == 5
    assert pipeline_run.records_valid == 4
    assert pipeline_run.records_quarantined == 1
    assert quarantine.raw_snapshot_id == snapshot.id
    assert "job_id" not in QuarantineRecord.__table__.columns
    assert "source_observation_id" not in QuarantineRecord.__table__.columns


@pytest.mark.asyncio
async def test_quarantine_traces_to_snapshot_run_source_and_company(
    db_session: AsyncSession,
) -> None:
    company, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    quarantine = build_quarantine_record(source, pipeline_run, snapshot)
    db_session.add(quarantine)
    await db_session.flush()
    quarantine_id = quarantine.id
    db_session.expunge_all()

    loaded = (
        await db_session.execute(
            select(QuarantineRecord)
            .options(
                joinedload(QuarantineRecord.raw_snapshot)
                .joinedload(RawSnapshot.pipeline_run)
                .joinedload(PipelineRun.source_connection)
                .joinedload(SourceConnection.company)
            )
            .where(QuarantineRecord.id == quarantine_id)
        )
    ).scalar_one()

    loaded_snapshot = loaded.raw_snapshot
    assert loaded_snapshot.id == snapshot.id
    assert loaded_snapshot.pipeline_run.id == pipeline_run.id
    assert loaded_snapshot.pipeline_run.source_connection.id == source.id
    assert loaded_snapshot.pipeline_run.source_connection.company.id == company.id


@pytest.mark.asyncio
async def test_snapshot_delete_is_restricted_while_quarantine_references_it(
    db_session: AsyncSession,
) -> None:
    _, source = await create_source(db_session)
    pipeline_run, snapshot = await create_run_and_snapshot(db_session, source)
    db_session.add(build_quarantine_record(source, pipeline_run, snapshot))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                delete(RawSnapshot).where(RawSnapshot.id == snapshot.id)
            )
