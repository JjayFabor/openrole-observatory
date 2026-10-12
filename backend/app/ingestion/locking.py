import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from hashlib import blake2b
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.pipeline_runs.errors import SourceSyncAlreadyRunningError

logger = logging.getLogger(__name__)


class SourceRunLock(Protocol):
    def hold(
        self,
        source_connection_id: UUID,
    ) -> AbstractAsyncContextManager[None]: ...


def advisory_lock_key(source_connection_id: UUID) -> int:
    """Map a UUID deterministically into PostgreSQL's signed bigint key space."""

    digest = blake2b(
        source_connection_id.bytes,
        digest_size=8,
        person=b"openrole-lock",
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


class PostgresSourceRunLock:
    """Hold a session advisory lock on one dedicated PostgreSQL connection."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def hold(self, source_connection_id: UUID) -> AsyncIterator[None]:
        lock_key = advisory_lock_key(source_connection_id)

        async with self._engine.connect() as pooled_connection:
            connection = await pooled_connection.execution_options(
                isolation_level="AUTOCOMMIT"
            )
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            if acquired is not True:
                logger.info(
                    "source_lock_contention",
                    extra={"source_connection_id": str(source_connection_id)},
                )
                raise SourceSyncAlreadyRunningError(source_connection_id)

            body_error: BaseException | None = None
            try:
                yield
            except BaseException as error:
                body_error = error
                raise
            finally:
                await self._release(
                    connection,
                    lock_key,
                    source_connection_id,
                    suppress_error=body_error is not None,
                )

    @staticmethod
    async def _release(
        connection: AsyncConnection,
        lock_key: int,
        source_connection_id: UUID,
        *,
        suppress_error: bool,
    ) -> None:
        try:
            released = await connection.scalar(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": lock_key},
            )
            if released is not True:
                logger.warning(
                    "source_lock_not_held_during_release",
                    extra={"source_connection_id": str(source_connection_id)},
                )
        except BaseException:
            await connection.invalidate()
            logger.exception(
                "source_lock_release_failed",
                extra={"source_connection_id": str(source_connection_id)},
            )
            if not suppress_error:
                raise
