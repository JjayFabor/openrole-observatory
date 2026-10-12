from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.pipeline_runs import router as pipeline_runs_router
from app.api.public_jobs import router as public_jobs_router
from app.api.quarantine import router as quarantine_router
from app.api.source_sync import router as source_sync_router
from app.api.sources import router as sources_router
from app.composition import build_runtime_services
from app.config import Settings, get_settings
from app.database.engine import create_database_engine
from app.database.session import create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    database_engine = create_database_engine(application_settings.database_url)
    db_session_factory = create_session_factory(database_engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        application.state.settings = application_settings
        application.state.database_engine = database_engine
        application.state.db_session_factory = db_session_factory

        try:
            async with build_runtime_services(
                settings=application_settings,
                database_engine=database_engine,
                session_factory=db_session_factory,
            ) as services:
                application.state.source_sync_service = services.source_sync
                application.state.pipeline_run_query_service = (
                    services.pipeline_run_queries
                )
                application.state.job_query_service = services.job_queries
                application.state.public_job_query_service = services.public_job_queries
                application.state.source_query_service = services.source_queries
                application.state.quarantine_query_service = services.quarantine_queries
                yield
        finally:
            await database_engine.dispose()

    application = FastAPI(
        title="OpenRole Observatory",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(source_sync_router)
    application.include_router(pipeline_runs_router)
    application.include_router(jobs_router)
    application.include_router(public_jobs_router)
    application.include_router(sources_router)
    application.include_router(quarantine_router)
    return application


app = create_app()
