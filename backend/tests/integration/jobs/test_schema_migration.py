from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import get_settings
from app.database.engine import create_database_engine
from tests.test_jobs import OBSERVED_AT

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PHASE_ONE_HEAD = "3e7f3cd24003"
TASK_24_HEAD = "55c52c19c673"
PHASE_ONE_TABLES = {
    "companies",
    "source_connections",
    "pipeline_runs",
    "raw_snapshots",
    "source_observations",
    "jobs",
    "job_versions",
    "quarantine_records",
}
Snapshot = dict[str, list[dict[str, object]]]


def migrate(connection: Connection, *, revision: str, downgrade: bool = False) -> None:
    # No logging config file: in-process migrations must preserve pytest's log capture.
    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.attributes["connection"] = connection
    if downgrade:
        command.downgrade(config, revision)
    else:
        command.upgrade(config, revision)


def seed_phase_one(connection: Connection) -> None:
    """Insert valid historical rows using the actual Phase 1 migrated schema."""
    metadata = MetaData()
    metadata.reflect(bind=connection)
    company_id, source_id, run_id, snapshot_id, observation_id, job_id = (
        uuid4() for _ in range(6)
    )
    connection.execute(
        metadata.tables["companies"]
        .insert()
        .values(
            id=company_id,
            name="Migration test company",
            slug="migration-test",
        )
    )
    connection.execute(
        metadata.tables["source_connections"]
        .insert()
        .values(
            id=source_id,
            company_id=company_id,
            provider="greenhouse",
            external_account_key="migration-test",
        )
    )
    connection.execute(
        metadata.tables["pipeline_runs"]
        .insert()
        .values(
            id=run_id,
            source_connection_id=source_id,
            status="completed_with_errors",
            started_at=OBSERVED_AT,
            completed_at=OBSERVED_AT,
        )
    )
    connection.execute(
        metadata.tables["raw_snapshots"]
        .insert()
        .values(
            id=snapshot_id,
            pipeline_run_id=run_id,
            r2_object_key="bronze/migration/jobs.json",
            content_hash="f" * 64,
            content_type="application/json",
            retrieved_at=OBSERVED_AT,
        )
    )
    connection.execute(
        metadata.tables["source_observations"]
        .insert()
        .values(
            id=observation_id,
            pipeline_run_id=run_id,
            source_connection_id=source_id,
            raw_snapshot_id=snapshot_id,
            external_job_id="1001",
            observed_at=OBSERVED_AT,
        )
    )
    connection.execute(
        metadata.tables["jobs"]
        .insert()
        .values(
            id=job_id,
            company_id=company_id,
            source_connection_id=source_id,
            external_job_id="1001",
            first_seen_at=OBSERVED_AT,
            last_seen_at=OBSERVED_AT,
            lifecycle_status="not_observed",
            no_longer_observed_at=OBSERVED_AT,
            reappeared_at=OBSERVED_AT,
        )
    )
    connection.execute(
        metadata.tables["job_versions"]
        .insert()
        .values(
            id=uuid4(),
            job_id=job_id,
            source_observation_id=observation_id,
            version_number=1,
            content_hash="a" * 64,
            title="Backend Engineer",
            source_url="https://example.com/jobs/1001",
            effective_from=OBSERVED_AT,
            canonical_metadata={"departments": ["Engineering"]},
        )
    )
    connection.execute(
        metadata.tables["quarantine_records"]
        .insert()
        .values(
            id=uuid4(),
            pipeline_run_id=run_id,
            source_connection_id=source_id,
            raw_snapshot_id=snapshot_id,
            error_category="record_validation_failed",
            error_message="Invalid record",
            raw_record_locator="jobs[1]",
        )
    )


def capture_phase_one(connection: Connection) -> Snapshot:
    metadata = MetaData()
    metadata.reflect(bind=connection, only=sorted(PHASE_ONE_TABLES))
    result: Snapshot = {}
    for name in sorted(PHASE_ONE_TABLES):
        # Compare only Phase 1 columns even when Task 24 adds columns to jobs.
        table = metadata.tables[name]
        columns = [
            column
            for column in table.columns
            if column.name
            not in {
                "consecutive_absent_runs",
                "absence_first_detected_at",
            }
        ]
        result[name] = [
            dict(row)
            for row in connection.execute(
                select(*columns).order_by(table.c.id)
            ).mappings()
        ]
    return result


async def table_names(connection: AsyncConnection) -> set[str]:
    return await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))


@pytest.mark.asyncio
async def test_task_24_upgrade_backfills_and_downgrade_preserves_phase_one() -> None:
    engine = create_database_engine(get_settings().database_url)
    schema_name = f"task_24_migration_{uuid4().hex}"

    try:
        async with engine.connect() as connection:
            # One transaction owns this disposable namespace, including all Alembic DDL.
            # Rolling it back removes the test schema without touching developer tables.
            transaction = await connection.begin()
            try:
                await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
                await connection.execute(
                    text(f'SET LOCAL search_path TO "{schema_name}"')
                )
                await connection.run_sync(migrate, revision=PHASE_ONE_HEAD)
                assert await table_names(connection) == PHASE_ONE_TABLES | {
                    "alembic_version"
                }
                await connection.run_sync(seed_phase_one)
                original = await connection.run_sync(capture_phase_one)

                await connection.run_sync(migrate, revision=TASK_24_HEAD)
                assert await table_names(connection) == PHASE_ONE_TABLES | {
                    "alembic_version",
                    "job_change_events",
                    "job_lifecycle_events",
                }
                assert await connection.run_sync(capture_phase_one) == original
                defaults = (
                    await connection.execute(
                        text(
                            "SELECT consecutive_absent_runs, absence_first_detected_at FROM jobs"
                        )
                    )
                ).one()
                assert tuple(defaults) == (0, None)

                # SQL bypasses ORM defaults to verify PostgreSQL defaults for new rows.
                new_job_id = uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO jobs (id, company_id, source_connection_id, external_job_id, "
                        "first_seen_at, last_seen_at) "
                        "SELECT :id, company_id, source_connection_id, '1002', first_seen_at, "
                        "last_seen_at FROM jobs WHERE external_job_id = '1001'"
                    ),
                    {"id": new_job_id},
                )
                defaults = (
                    await connection.execute(
                        text(
                            "SELECT consecutive_absent_runs, absence_first_detected_at "
                            "FROM jobs WHERE id = :id"
                        ),
                        {"id": new_job_id},
                    )
                ).one()
                assert tuple(defaults) == (0, None)

                event_id = uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO job_lifecycle_events (id, job_id, pipeline_run_id, "
                        "event_type, occurred_at) "
                        "SELECT :id, jobs.id, pipeline_runs.id, 'absence_detected', :at "
                        "FROM jobs CROSS JOIN pipeline_runs WHERE jobs.external_job_id = '1001'"
                    ),
                    {"id": event_id, "at": OBSERVED_AT},
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT metadata FROM job_lifecycle_events WHERE id = :id"
                        ),
                        {"id": event_id},
                    )
                    == {}
                )
                before_downgrade = await connection.run_sync(capture_phase_one)

                await connection.run_sync(
                    migrate, revision=PHASE_ONE_HEAD, downgrade=True
                )
                assert await table_names(connection) == PHASE_ONE_TABLES | {
                    "alembic_version"
                }
                columns = await connection.run_sync(
                    lambda sync: {
                        column["name"] for column in inspect(sync).get_columns("jobs")
                    }
                )
                assert "consecutive_absent_runs" not in columns
                assert "absence_first_detected_at" not in columns
                assert await connection.run_sync(capture_phase_one) == before_downgrade
                assert (
                    await connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                    == PHASE_ONE_HEAD
                )

                await connection.run_sync(migrate, revision=TASK_24_HEAD)
                assert await connection.run_sync(capture_phase_one) == before_downgrade
                assert (
                    await connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                    == TASK_24_HEAD
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
