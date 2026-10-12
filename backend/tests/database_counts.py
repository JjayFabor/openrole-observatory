from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.database.base import Base
from app.database.models import REGISTERED_MODELS

TableCounts = dict[str, int]


async def capture_table_counts(connection: AsyncConnection) -> TableCounts:
    counts: TableCounts = {}
    for model in REGISTERED_MODELS:
        count = await connection.scalar(select(func.count()).select_from(model))
        assert count is not None
        counts[model.__tablename__] = count
    return counts


async def count_rows_since_baseline(
    session_factory: async_sessionmaker[AsyncSession],
    model: type[Base],
    baseline: TableCounts,
) -> int:
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(model))
    assert count is not None
    return count - baseline[model.__tablename__]
