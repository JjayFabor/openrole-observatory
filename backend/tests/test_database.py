import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.database.engine import create_database_engine
from app.database.session import create_session_factory


@pytest.mark.asyncio
async def test_async_session_executes_query_against_postgres() -> None:
    engine = create_database_engine(get_settings().database_url)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            result = await session.execute(text("SELECT 1"))

        assert result.scalar_one() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_errors_hide_bound_job_content() -> None:
    engine = create_database_engine(get_settings().database_url)
    try:
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError) as caught:
                await connection.execute(
                    text("SELECT CAST(:description AS TEXT), 1 / :divisor"),
                    {"description": "private-job-description", "divisor": 0},
                )
        assert "private-job-description" not in str(caught.value)
        assert "parameters hidden" in str(caught.value)
    finally:
        await engine.dispose()
