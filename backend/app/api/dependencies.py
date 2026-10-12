from typing import Annotated, cast

from fastapi import Depends, Request

from app.ingestion.sync import SourceSyncService
from app.jobs.public_query_service import PublicJobQueryService
from app.jobs.query_service import JobQueryService
from app.pipeline_runs.query_service import PipelineRunQueryService
from app.quarantine.query_service import QuarantineQueryService
from app.sources.query_service import SourceQueryService


def get_source_sync_service(request: Request) -> SourceSyncService:
    return cast(SourceSyncService, request.app.state.source_sync_service)


def get_pipeline_run_query_service(request: Request) -> PipelineRunQueryService:
    return cast(
        PipelineRunQueryService,
        request.app.state.pipeline_run_query_service,
    )


SourceSyncDependency = Annotated[
    SourceSyncService,
    Depends(get_source_sync_service),
]
PipelineRunQueryDependency = Annotated[
    PipelineRunQueryService,
    Depends(get_pipeline_run_query_service),
]


def get_job_query_service(request: Request) -> JobQueryService:
    return cast(JobQueryService, request.app.state.job_query_service)


def get_source_query_service(request: Request) -> SourceQueryService:
    return cast(SourceQueryService, request.app.state.source_query_service)


JobQueryDependency = Annotated[JobQueryService, Depends(get_job_query_service)]


def get_public_job_query_service(request: Request) -> PublicJobQueryService:
    return cast(PublicJobQueryService, request.app.state.public_job_query_service)


PublicJobQueryDependency = Annotated[
    PublicJobQueryService, Depends(get_public_job_query_service)
]
SourceQueryDependency = Annotated[SourceQueryService, Depends(get_source_query_service)]


def get_quarantine_query_service(request: Request) -> QuarantineQueryService:
    return cast(QuarantineQueryService, request.app.state.quarantine_query_service)


QuarantineQueryDependency = Annotated[
    QuarantineQueryService, Depends(get_quarantine_query_service)
]
