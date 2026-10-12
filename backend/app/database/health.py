import logging
from typing import cast

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def check_database_connection(engine: AsyncEngine) -> bool:
    """Return whether PostgreSQL can execute a non-mutating probe query."""

    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            return result.scalar_one() == 1
    except Exception as error:
        logger.warning(
            "Database readiness check failed",
            extra={
                "event": "database_readiness_check_failed",
                "error_type": type(error).__name__,
            },
        )
        return False


async def get_database_readiness(request: Request) -> bool:
    """FastAPI dependency that checks the application's shared engine."""

    engine = cast(AsyncEngine, request.app.state.database_engine)
    return await check_database_connection(engine)
