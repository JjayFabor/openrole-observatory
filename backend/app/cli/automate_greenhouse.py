"""One automation cycle, suitable for an external six-hour scheduler."""

import argparse
import asyncio
import json
import logging
from collections.abc import Sequence
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from pydantic import BaseModel

from app.composition import build_runtime_services
from app.config import get_settings
from app.database.engine import create_database_engine
from app.database.session import create_session_factory
from app.ingestion.locking import PostgresSourceRunLock
from app.ingestion.source_automation import (
    DiscoveryReport,
    SynchronizationReport,
    discover_boards,
    synchronize_active_sources,
)
from app.pipeline_runs.errors import SourceSyncAlreadyRunningError
from app.sources.greenhouse.client import GreenhouseClient
from app.sources.greenhouse.discovery import (
    DEFAULT_DIRECTORY_URL,
    validate_directory_url,
)
from app.storage.factory import create_object_storage

# Reserved only as a lock scope; it is never inserted as a SourceConnection ID.
AUTOMATION_LOCK_SCOPE = uuid5(NAMESPACE_URL, "openrole:greenhouse-source-automation")
logger = logging.getLogger(__name__)


class AutomationReport(BaseModel):
    cycle_id: UUID
    discovery: DiscoveryReport
    synchronization: SynchronizationReport

    @property
    def has_errors(self) -> bool:
        return bool(
            self.discovery.failures
            or self.discovery.invalid_rows
            or self.synchronization.failures
            or self.synchronization.completed_with_errors
        )


async def run(*, directory_url: str, max_new_sources: int, request_delay: float) -> int:
    validate_directory_url(directory_url)
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    factory = create_session_factory(engine)
    cycle_id = uuid4()
    try:
        async with PostgresSourceRunLock(engine).hold(AUTOMATION_LOCK_SCOPE):
            async with httpx.AsyncClient() as client:
                discovery = await discover_boards(
                    factory,
                    http_client=client,
                    greenhouse=GreenhouseClient(client),
                    storage=create_object_storage(settings),
                    directory_url=directory_url,
                    cycle_id=cycle_id,
                    max_new_sources=max_new_sources,
                    request_delay=request_delay,
                )
            # A catalogue outage does not prevent refreshing configured sources.
            async with build_runtime_services(
                settings=settings,
                database_engine=engine,
                session_factory=factory,
            ) as services:
                synchronization = await synchronize_active_sources(
                    factory,
                    services.source_sync.sync_source,
                    request_delay=request_delay,
                )
            report = AutomationReport(
                cycle_id=cycle_id,
                discovery=discovery,
                synchronization=synchronization,
            )
            print(report.model_dump_json(indent=2))
            return 1 if report.has_errors else 0
    except SourceSyncAlreadyRunningError:
        print(json.dumps({"status": "skipped", "code": "AUTOMATION_ALREADY_RUNNING"}))
        return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover and sync Greenhouse sources."
    )
    parser.add_argument("--directory-url", default=DEFAULT_DIRECTORY_URL)
    parser.add_argument("--max-new-sources", type=int, default=25)
    parser.add_argument("--request-delay", type=float, default=0.5)
    args = parser.parse_args(argv)
    if not 0 <= args.max_new_sources <= 1000 or not 0 <= args.request_delay <= 60:
        parser.error(
            "max-new-sources must be 0–1000; request-delay must be 0–60 seconds"
        )
    try:
        return asyncio.run(
            run(
                directory_url=args.directory_url,
                max_new_sources=args.max_new_sources,
                request_delay=args.request_delay,
            )
        )
    except Exception as error:
        logger.error(
            "source_automation_failed", extra={"error_type": type(error).__name__}
        )
        print(json.dumps({"status": "failed", "code": "AUTOMATION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
