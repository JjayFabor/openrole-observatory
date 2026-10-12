import logging
import time
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.errors import (
    PipelineRunNotRunningError,
    PipelineRunSourceMismatchError,
    RawSnapshotAlreadyExistsError,
    RawSnapshotPersistenceError,
    UnsupportedSourceProviderError,
)
from app.pipeline_runs.errors import (
    PipelineRunNotFoundError,
    SourceConnectionInactiveError,
)
from app.pipeline_runs.models import PipelineRunStatus
from app.raw_snapshots.keys import build_raw_snapshot_key
from app.raw_snapshots.models import RawSnapshot
from app.raw_snapshots.repository import (
    RawAcquisitionContext,
    RawSnapshotRepository,
)
from app.sources.greenhouse.client import GreenhouseFetchResult
from app.sources.models import SourceProvider
from app.storage.base import ObjectStorage, StoredObject

logger = logging.getLogger(__name__)

DEFAULT_GREENHOUSE_CONTENT_TYPE = "application/json"


class GreenhouseJobsFetcher(Protocol):
    async def fetch_jobs(self, *, board_token: str) -> GreenhouseFetchResult: ...


class RawSnapshotAcquisitionService:
    """Fetch and preserve one running Greenhouse pipeline run's raw response."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        greenhouse_client: GreenhouseJobsFetcher,
        object_storage: ObjectStorage,
    ) -> None:
        self._session_factory = session_factory
        self._greenhouse_client = greenhouse_client
        self._object_storage = object_storage

    async def acquire(
        self,
        *,
        pipeline_run_id: UUID,
        source_connection_id: UUID,
    ) -> RawSnapshot:
        context = await self._load_context(pipeline_run_id)
        self._validate_context(context, source_connection_id)

        log_fields = {
            "pipeline_run_id": str(pipeline_run_id),
            "source_connection_id": str(source_connection_id),
            "provider": context.provider,
        }
        logger.info("raw_source_fetch_started", extra=log_fields)
        fetch_started = time.monotonic()
        fetch_result = await self._greenhouse_client.fetch_jobs(
            board_token=context.external_account_key
        )
        fetch_duration_ms = round((time.monotonic() - fetch_started) * 1000)
        logger.info(
            "raw_source_fetch_completed",
            extra={
                **log_fields,
                "status_code": fetch_result.status_code,
                "content_length_bytes": len(fetch_result.body),
                "duration_ms": fetch_duration_ms,
            },
        )

        object_key = build_raw_snapshot_key(
            provider=context.provider,
            source_connection_id=context.source_connection_id,
            pipeline_run_id=context.pipeline_run_id,
            retrieved_at=fetch_result.retrieved_at,
        )
        stored_object = await self._object_storage.put_bytes(
            key=object_key,
            data=fetch_result.body,
            content_type=(fetch_result.content_type or DEFAULT_GREENHOUSE_CONTENT_TYPE),
        )
        logger.info(
            "raw_snapshot_stored",
            extra={
                **log_fields,
                "object_key": stored_object.key,
                "content_length_bytes": stored_object.content_length_bytes,
            },
        )

        try:
            raw_snapshot = await self._persist_snapshot(
                pipeline_run_id=pipeline_run_id,
                source_connection_id=source_connection_id,
                stored_object=stored_object,
                retrieved_at=fetch_result.retrieved_at.astimezone(UTC),
            )
        except SQLAlchemyError as error:
            logger.exception(
                "raw_snapshot_persistence_failed",
                extra={**log_fields, "object_key": stored_object.key},
            )
            raise RawSnapshotPersistenceError(
                pipeline_run_id,
                stored_object.key,
            ) from error
        except Exception:
            logger.exception(
                "raw_snapshot_persistence_failed",
                extra={**log_fields, "object_key": stored_object.key},
            )
            raise

        logger.info(
            "raw_snapshot_persisted",
            extra={
                **log_fields,
                "raw_snapshot_id": str(raw_snapshot.id),
                "object_key": raw_snapshot.r2_object_key,
                "content_length_bytes": raw_snapshot.content_length_bytes,
            },
        )
        return raw_snapshot

    async def _load_context(self, pipeline_run_id: UUID) -> RawAcquisitionContext:
        async with self._session_factory() as session:
            context = await RawSnapshotRepository(session).get_acquisition_context(
                pipeline_run_id
            )
        if context is None:
            raise PipelineRunNotFoundError(pipeline_run_id)
        return context

    async def _persist_snapshot(
        self,
        *,
        pipeline_run_id: UUID,
        source_connection_id: UUID,
        stored_object: StoredObject,
        retrieved_at: datetime,
    ) -> RawSnapshot:
        async with self._session_factory.begin() as session:
            repository = RawSnapshotRepository(session)
            context = await repository.get_acquisition_context(
                pipeline_run_id,
                for_update=True,
            )
            if context is None:
                raise PipelineRunNotFoundError(pipeline_run_id)
            self._validate_context(context, source_connection_id)

            raw_snapshot = RawSnapshot(
                pipeline_run_id=pipeline_run_id,
                r2_object_key=stored_object.key,
                content_hash=stored_object.content_hash,
                content_type=stored_object.content_type,
                content_length_bytes=stored_object.content_length_bytes,
                record_count=None,
                retrieved_at=retrieved_at,
            )
            await repository.create(raw_snapshot)

        return raw_snapshot

    @staticmethod
    def _validate_context(
        context: RawAcquisitionContext,
        supplied_source_connection_id: UUID,
    ) -> None:
        if context.source_connection_id != supplied_source_connection_id:
            raise PipelineRunSourceMismatchError(
                context.pipeline_run_id,
                context.source_connection_id,
                supplied_source_connection_id,
            )
        if context.raw_snapshot_id is not None:
            raise RawSnapshotAlreadyExistsError(context.pipeline_run_id)
        if context.pipeline_run_status != PipelineRunStatus.RUNNING.value:
            raise PipelineRunNotRunningError(
                context.pipeline_run_id,
                context.pipeline_run_status,
            )
        if not context.source_is_active:
            raise SourceConnectionInactiveError(context.source_connection_id)
        if context.provider != SourceProvider.GREENHOUSE.value:
            raise UnsupportedSourceProviderError(context.provider)
