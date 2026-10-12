from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import SourceQueryDependency
from app.api.errors import APIErrorResponse, api_error_response
from app.sources.models import SourceProvider
from app.sources.read_schemas import SourceListItem, SourceListRead

router = APIRouter(prefix="/api/v1/sources", tags=["source-inspection"])


@router.get("", response_model=SourceListRead)
async def list_sources(
    service: SourceQueryDependency,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2_147_483_647),
    is_active: bool | None = None,
    provider: SourceProvider | None = None,
) -> SourceListRead:
    return await service.list(
        limit=limit, offset=offset, is_active=is_active, provider=provider
    )


@router.get(
    "/{source_id}",
    response_model=SourceListItem,
    responses={404: {"model": APIErrorResponse}},
    summary="Inspect source freshness and its latest pipeline run",
    description=(
        "The latest run is selected by started_at descending, then ID descending. "
        "An attempted or failed run does not imply a successful synchronization. "
        "Safe company identity fields are included. Source configuration and "
        "external account keys are excluded."
    ),
)
async def get_source(
    source_id: UUID, request: Request, service: SourceQueryDependency
) -> SourceListItem | JSONResponse:
    source = await service.get(source_id)
    if source is None:
        return api_error_response(
            request,
            status_code=404,
            code="SOURCE_CONNECTION_NOT_FOUND",
            message="The source connection was not found.",
        )
    return source
