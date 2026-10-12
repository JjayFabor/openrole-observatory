from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.database.engine import create_database_engine
from app.ingestion.locking import PostgresSourceRunLock, advisory_lock_key
from app.pipeline_runs.errors import SourceSyncAlreadyRunningError


@pytest_asyncio.fixture
async def database_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(get_settings().database_url)
    yield engine
    await engine.dispose()


def test_advisory_lock_key_is_stable_and_source_specific() -> None:
    source_id = UUID("12345678-1234-5678-1234-567812345678")

    assert advisory_lock_key(source_id) == -6062847268196138555
    assert advisory_lock_key(source_id) == advisory_lock_key(source_id)
    assert advisory_lock_key(source_id) != advisory_lock_key(uuid4())


@pytest.mark.asyncio
async def test_same_source_cannot_hold_two_locks(
    database_engine: AsyncEngine,
) -> None:
    source_id = uuid4()
    source_lock = PostgresSourceRunLock(database_engine)

    async with source_lock.hold(source_id):
        with pytest.raises(SourceSyncAlreadyRunningError) as exc_info:
            async with source_lock.hold(source_id):
                pytest.fail("a second lock for the same source was acquired")

    assert exc_info.value.code == "SOURCE_SYNC_ALREADY_RUNNING"


@pytest.mark.asyncio
async def test_different_sources_can_hold_locks_concurrently(
    database_engine: AsyncEngine,
) -> None:
    source_lock = PostgresSourceRunLock(database_engine)

    async with source_lock.hold(uuid4()), source_lock.hold(uuid4()):
        pass


@pytest.mark.asyncio
async def test_lock_is_released_after_success(database_engine: AsyncEngine) -> None:
    source_id = uuid4()
    source_lock = PostgresSourceRunLock(database_engine)

    async with source_lock.hold(source_id):
        pass

    async with source_lock.hold(source_id):
        pass


@pytest.mark.asyncio
async def test_lock_is_released_after_exception(database_engine: AsyncEngine) -> None:
    source_id = uuid4()
    source_lock = PostgresSourceRunLock(database_engine)

    with pytest.raises(RuntimeError, match="simulated pipeline failure"):
        async with source_lock.hold(source_id):
            raise RuntimeError("simulated pipeline failure")

    async with source_lock.hold(source_id):
        pass
