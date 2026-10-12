from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import QuarantineQueryDependency
from app.api.errors import APIErrorResponse, api_error_response
from app.quarantine.models import QuarantineStatus
from app.quarantine.read_schemas import QuarantineList, QuarantineRecordDetail

router = APIRouter(prefix="/api/v1/quarantine", tags=["quarantine-inspection"])


@router.get("", response_model=QuarantineList)
async def list_quarantine_records(
    service: QuarantineQueryDependency,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2_147_483_647),
    status: QuarantineStatus | None = None,
    pipeline_run_id: UUID | None = None,
    source_connection_id: UUID | None = None,
    error_category: str | None = Query(default=None, max_length=100),
) -> QuarantineList:
    return await service.list(
        limit=limit,
        offset=offset,
        status=status,
        pipeline_run_id=pipeline_run_id,
        source_connection_id=source_connection_id,
        error_category=error_category,
    )


@router.get(
    "/{record_id}",
    response_model=QuarantineRecordDetail,
    responses={404: {"model": APIErrorResponse}},
)
async def get_quarantine_record(
    record_id: UUID, request: Request, service: QuarantineQueryDependency
) -> QuarantineRecordDetail | JSONResponse:
    record = await service.get(record_id)
    if record is None:
        return api_error_response(
            request,
            status_code=404,
            code="QUARANTINE_RECORD_NOT_FOUND",
            message="The quarantined record was not found.",
        )
    return record
