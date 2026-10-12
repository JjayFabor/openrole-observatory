from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_database_engine(database_url: str) -> AsyncEngine:
    """Create the shared async engine without opening a connection yet."""

    return create_async_engine(database_url, pool_pre_ping=True, hide_parameters=True)
