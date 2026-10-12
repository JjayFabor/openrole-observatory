from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.ingestion.locking import PostgresSourceRunLock
from app.ingestion.orchestration import SnapshotIngestionOrchestrator
from app.ingestion.raw_acquisition import RawSnapshotAcquisitionService
from app.ingestion.sync import SourceSyncService
from app.jobs.absence_confirmation import AbsenceConfirmationService
from app.jobs.lifecycle_reconciliation import LifecycleReconciliationService
from app.jobs.public_query_service import PublicJobQueryService
from app.jobs.query_service import JobQueryService
from app.pipeline_runs.query_service import PipelineRunQueryService
from app.pipeline_runs.service import PipelineRunService
from app.quarantine.query_service import QuarantineQueryService
from app.sources.greenhouse.client import GreenhouseClient
from app.sources.query_service import SourceQueryService
from app.storage.factory import create_object_storage


@dataclass(frozen=True, slots=True)
class RuntimeServices:
    source_sync: SourceSyncService
    pipeline_run_queries: PipelineRunQueryService
    job_queries: JobQueryService
    source_queries: SourceQueryService
    quarantine_queries: QuarantineQueryService
    public_job_queries: PublicJobQueryService


@asynccontextmanager
async def build_runtime_services(
    *,
    settings: Settings,
    database_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[RuntimeServices]:
    """Wire shared concrete services for both FastAPI and CLI adapters."""

    object_storage = create_object_storage(settings)
    async with httpx.AsyncClient() as http_client:
        greenhouse_client = GreenhouseClient(
            http_client,
            connect_timeout_seconds=settings.http_connect_timeout_seconds,
            read_timeout_seconds=settings.http_read_timeout_seconds,
        )
        pipeline_runs = PipelineRunService(session_factory)
        raw_acquisition = RawSnapshotAcquisitionService(
            session_factory,
            greenhouse_client=greenhouse_client,
            object_storage=object_storage,
        )
        snapshot_orchestrator = SnapshotIngestionOrchestrator(
            session_factory,
            object_storage=object_storage,
            pipeline_run_service=pipeline_runs,
        )
        source_sync = SourceSyncService(
            session_factory,
            source_run_lock=PostgresSourceRunLock(database_engine),
            pipeline_run_service=pipeline_runs,
            raw_acquisition_service=raw_acquisition,
            snapshot_orchestrator=snapshot_orchestrator,
            lifecycle_reconciliation=LifecycleReconciliationService(
                session_factory,
                absence_confirmation=AbsenceConfirmationService(
                    session_factory, settings=settings
                ),
            ),
        )
        yield RuntimeServices(
            source_sync=source_sync,
            pipeline_run_queries=PipelineRunQueryService(session_factory),
            job_queries=JobQueryService(session_factory),
            source_queries=SourceQueryService(session_factory),
            quarantine_queries=QuarantineQueryService(session_factory),
            public_job_queries=PublicJobQueryService(session_factory),
        )
