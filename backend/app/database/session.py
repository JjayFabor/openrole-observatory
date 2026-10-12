from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database.models import register_models


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create sessions whose loaded values remain usable after a commit."""

    register_models()
    return async_sessionmaker(engine, expire_on_commit=False)
