import subprocess
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.cli.seed_dev import seed_development_source
from app.companies.models import Company
from app.config import get_settings
from app.database.engine import create_database_engine
from app.sources.models import SourceConnection, SourceProvider
from tests.database_counts import (
    TableCounts,
    capture_table_counts,
    count_rows_since_baseline,
)


@dataclass(frozen=True, slots=True)
class DatabaseContext:
    engine: AsyncEngine
    connection: AsyncConnection
    session_factory: async_sessionmaker[AsyncSession]
    baseline_counts: TableCounts


def test_seed_cli_registers_all_orm_models_in_a_fresh_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from sqlalchemy.orm import configure_mappers; "
                "from app.database.engine import create_database_engine; "
                "from app.database.session import create_session_factory; "
                "engine = create_database_engine("
                "'postgresql+asyncpg://openrole:openrole@localhost/openrole'); "
                "create_session_factory(engine); configure_mappers()"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


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


@pytest.mark.asyncio
async def test_seed_development_source_is_idempotent(
    database_context: DatabaseContext,
) -> None:
    first = await seed_development_source(
        database_context.session_factory,
        board_token="example-board",
        company_name="Example Company",
        company_slug="Example-Company",
    )
    second = await seed_development_source(
        database_context.session_factory,
        board_token="example-board",
        company_name="Ignored Duplicate Name",
        company_slug="ignored-duplicate-slug",
    )

    assert first.source_created is True
    assert second.source_created is False
    assert second == type(second)(
        company_id=first.company_id,
        source_connection_id=first.source_connection_id,
        source_created=False,
    )

    company_count = await count_rows_since_baseline(
        database_context.session_factory,
        Company,
        database_context.baseline_counts,
    )
    source_count = await count_rows_since_baseline(
        database_context.session_factory,
        SourceConnection,
        database_context.baseline_counts,
    )
    async with database_context.session_factory() as session:
        source = await session.get(SourceConnection, first.source_connection_id)

    assert company_count == 1
    assert source_count == 1
    assert source is not None
    assert source.provider == SourceProvider.GREENHOUSE.value
    assert source.external_account_key == "example-board"


@pytest.mark.asyncio
async def test_seed_reuses_company_slug_for_another_source(
    database_context: DatabaseContext,
) -> None:
    first = await seed_development_source(
        database_context.session_factory,
        board_token="board-one",
        company_name="Example Company",
        company_slug="example-company",
    )
    second = await seed_development_source(
        database_context.session_factory,
        board_token="board-two",
        company_name="Example Company",
        company_slug="example-company",
    )

    assert first.company_id == second.company_id
    assert first.source_connection_id != second.source_connection_id

    company_count = await count_rows_since_baseline(
        database_context.session_factory,
        Company,
        database_context.baseline_counts,
    )
    source_count = await count_rows_since_baseline(
        database_context.session_factory,
        SourceConnection,
        database_context.baseline_counts,
    )

    assert company_count == 1
    assert source_count == 2
