from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.dependencies import PipelineRunQueryDependency
from app.api.errors import APIErrorResponse, api_error_response
from app.pipeline_runs.models import PipelineRunStatus
from app.pipeline_runs.schemas import PipelineRunList, PipelineRunRead

router = APIRouter(prefix="/api/v1/pipeline-runs", tags=["pipeline-runs"])


@router.get("", response_model=PipelineRunList)
async def list_pipeline_runs(
    service: PipelineRunQueryDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2147483647),
    source_connection_id: UUID | None = None,
    status: PipelineRunStatus | None = None,
) -> PipelineRunList:
    items = await service.list(
        limit=limit,
        offset=offset,
        source_connection_id=source_connection_id,
        status=status,
    )
    return PipelineRunList(items=items, limit=limit, offset=offset)


@router.get(
    "/{run_id}",
    response_model=PipelineRunRead,
    responses={status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse}},
)
async def get_pipeline_run(
    run_id: UUID,
    request: Request,
    service: PipelineRunQueryDependency,
) -> PipelineRunRead | JSONResponse:
    run = await service.get(run_id)
    if run is None:
        return api_error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="PIPELINE_RUN_NOT_FOUND",
            message="The pipeline run was not found.",
        )
    return run
