"""Discovery and batch invocation; SourceSyncService retains all pipeline logic."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.errors import SourceSyncFailedError
from app.ingestion.sync import SourceSyncResult
from app.pipeline_runs.errors import (
    SourceConnectionInactiveError,
    SourceConnectionNotFoundError,
    SourceSyncAlreadyRunningError,
)
from app.pipeline_runs.models import PipelineRunStatus
from app.sources.discovery_registry import (
    find_greenhouse_source,
    register_discovered_board,
)
from app.sources.greenhouse.client import GreenhouseClient
from app.sources.greenhouse.discovery import (
    DirectoryError,
    fetch_directory,
    parse_candidates,
    parse_native_board,
)
from app.sources.greenhouse.errors import GreenhouseError
from app.sources.models import SourceConnection, SourceProvider
from app.storage.base import ObjectStorage
from app.storage.errors import StorageError

logger = logging.getLogger(__name__)
SyncSource = Callable[[UUID], Awaitable[SourceSyncResult]]
Sleeper = Callable[[float], Awaitable[None]]


class AutomationFailure(BaseModel):
    code: str
    token: str | None = None
    source_id: UUID | None = None


class DiscoveryReport(BaseModel):
    candidates: int = 0
    excluded_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    created: int = 0
    existing: int = 0
    deferred: int = 0
    directory_object_key: str | None = None
    failures: list[AutomationFailure] = Field(default_factory=list)


class SynchronizationReport(BaseModel):
    attempted: int = 0
    completed: int = 0
    completed_with_errors: int = 0
    busy_skipped: int = 0
    inactive_or_missing_skipped: int = 0
    jobs_new: int = 0
    jobs_changed: int = 0
    jobs_unchanged: int = 0
    failures: list[AutomationFailure] = Field(default_factory=list)


async def discover_boards(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    http_client: httpx.AsyncClient,
    greenhouse: GreenhouseClient,
    storage: ObjectStorage,
    directory_url: str,
    cycle_id: UUID,
    max_new_sources: int,
    request_delay: float = 0.5,
    sleep: Sleeper = asyncio.sleep,
) -> DiscoveryReport:
    if max_new_sources < 0 or request_delay < 0:
        raise ValueError("Discovery limits must not be negative.")
    report = DiscoveryReport()
    prefix = f"bronze/greenhouse/discovery/{cycle_id}"
    try:
        body = await fetch_directory(http_client, directory_url)
        snapshot = await storage.put_bytes(
            key=f"{prefix}/directory.jsonl",
            data=body,
            content_type="application/x-ndjson",
        )
        report.directory_object_key = snapshot.key
        candidates = parse_candidates(body)
    except DirectoryError as error:
        report.failures.append(AutomationFailure(code=error.code))
        return report
    except StorageError:
        report.failures.append(AutomationFailure(code="DISCOVERY_STORAGE_FAILED"))
        return report
    report.candidates = len(candidates.tokens)
    report.excluded_rows = candidates.excluded_rows
    report.invalid_rows = candidates.invalid_rows
    report.duplicate_rows = candidates.duplicate_rows
    for token in candidates.tokens:
        if await find_greenhouse_source(session_factory, token) is not None:
            report.existing += 1
            continue
        if report.created >= max_new_sources:
            report.deferred += 1
            continue
        try:
            metadata = await greenhouse.fetch_board(board_token=token)
            native_snapshot = await storage.put_bytes(
                key=f"{prefix}/boards/{token}.json",
                data=metadata.body,
                content_type=metadata.content_type or "application/json",
            )
            board = parse_native_board(metadata.body)
            registered = await register_discovered_board(
                session_factory,
                token=token,
                board=board,
                directory_url=directory_url,
                directory_snapshot=snapshot,
                board_snapshot=native_snapshot,
                discovered_at=datetime.now(UTC),
            )
            if registered.created:
                report.created += 1
            else:
                report.existing += 1
        except DirectoryError as error:
            report.failures.append(AutomationFailure(code=error.code, token=token))
        except GreenhouseError:
            report.failures.append(
                AutomationFailure(code="BOARD_REQUEST_FAILED", token=token)
            )
        except StorageError:
            report.failures.append(
                AutomationFailure(code="DISCOVERY_STORAGE_FAILED", token=token)
            )
        await sleep(request_delay)
    return report


async def synchronize_active_sources(
    session_factory: async_sessionmaker[AsyncSession],
    sync_source: SyncSource,
    *,
    request_delay: float = 0.5,
    batch_size: int = 100,
    sleep: Sleeper = asyncio.sleep,
) -> SynchronizationReport:
    if request_delay < 0 or not 1 <= batch_size <= 1000:
        raise ValueError("Invalid source synchronization bounds.")
    report = SynchronizationReport()
    after: UUID | None = None
    while True:
        query = (
            select(SourceConnection.id)
            .where(
                SourceConnection.provider == SourceProvider.GREENHOUSE.value,
                SourceConnection.is_active.is_(True),
            )
            .order_by(SourceConnection.id)
            .limit(batch_size)
        )
        if after is not None:
            query = query.where(SourceConnection.id > after)
        async with session_factory() as session:
            ids = list(await session.scalars(query))
        if not ids:
            return report
        for source_id in ids:
            report.attempted += 1
            try:
                result = await sync_source(source_id)
                if result.source_connection_id != source_id:
                    raise ValueError("Unexpected source in synchronization result")
                if result.status == PipelineRunStatus.COMPLETED:
                    report.completed += 1
                elif result.status == PipelineRunStatus.COMPLETED_WITH_ERRORS:
                    report.completed_with_errors += 1
                else:
                    raise ValueError("Unexpected terminal synchronization status")
                report.jobs_new += result.jobs_new
                report.jobs_changed += result.jobs_changed
                report.jobs_unchanged += result.jobs_unchanged
            except SourceSyncAlreadyRunningError:
                report.busy_skipped += 1
            except (SourceConnectionInactiveError, SourceConnectionNotFoundError):
                report.inactive_or_missing_skipped += 1
            except SourceSyncFailedError as error:
                report.failures.append(
                    AutomationFailure(code=error.code, source_id=source_id)
                )
            except Exception as error:
                # Unexpected failure is visible; it must not hide later sources.
                logger.error(
                    "automatic_source_sync_failed",
                    extra={
                        "source_id": str(source_id),
                        "error_type": type(error).__name__,
                    },
                )
                report.failures.append(
                    AutomationFailure(
                        code="AUTOMATION_SYNC_FAILED", source_id=source_id
                    )
                )
            await sleep(request_delay)
        after = ids[-1]
