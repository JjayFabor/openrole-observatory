import logging
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import JobQueryDependency
from app.api.errors import APIErrorResponse, api_error_response
from app.jobs.errors import (
    CurrentJobVersionInvariantError,
    CurrentJobVersionMissingError,
)
from app.jobs.models import JobLifecycleStatus
from app.jobs.read_schemas import (
    JobChangeList,
    JobDetailRead,
    JobLifecycleRead,
    JobList,
    JobVersionList,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["job-inspection"])


def _job_not_found(request: Request) -> JSONResponse:
    return api_error_response(
        request,
        status_code=404,
        code="JOB_NOT_FOUND",
        message="The job was not found.",
    )


@router.get(
    "",
    response_model=JobList,
    responses={500: {"model": APIErrorResponse}},
    summary="List job identities with their current canonical display fields",
    description=(
        "Ordered by last_seen_at descending, then job ID ascending. "
        "q matches literal text, case-insensitively, in current title/location "
        "or external job ID. total counts all matching identities."
    ),
)
async def list_jobs(
    request: Request,
    service: JobQueryDependency,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2_147_483_647),
    lifecycle_status: JobLifecycleStatus | None = None,
    source_connection_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
) -> JobList | JSONResponse:
    try:
        return await service.list(
            limit=limit,
            offset=offset,
            lifecycle_status=lifecycle_status,
            source_connection_id=source_connection_id,
            q=q,
        )
    except (CurrentJobVersionMissingError, CurrentJobVersionInvariantError) as error:
        logger.error("job_list_current_version_invariant_failed")
        return api_error_response(
            request,
            status_code=500,
            code=error.code,
            message="The jobs' current canonical versions are inconsistent.",
        )


@router.get(
    "/{job_id}",
    response_model=JobDetailRead,
    responses={404: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}},
    summary="Inspect job identity, lifecycle state, and current canonical version",
)
async def get_job(
    job_id: UUID, request: Request, service: JobQueryDependency
) -> JobDetailRead | JSONResponse:
    try:
        job = await service.get(job_id)
    except (CurrentJobVersionMissingError, CurrentJobVersionInvariantError) as error:
        logger.error(
            "job_current_version_invariant_failed", extra={"job_id": str(job_id)}
        )
        return api_error_response(
            request,
            status_code=500,
            code=error.code,
            message="The job's current canonical version is inconsistent.",
        )
    return job if job is not None else _job_not_found(request)


@router.get(
    "/{job_id}/versions",
    response_model=JobVersionList,
    responses={404: {"model": APIErrorResponse}},
    summary="Inspect canonical versions in ascending version-number order",
)
async def list_job_versions(
    job_id: UUID,
    request: Request,
    service: JobQueryDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobVersionList | JSONResponse:
    result = await service.versions(job_id, limit=limit, offset=offset)
    return result if result is not None else _job_not_found(request)


@router.get(
    "/{job_id}/changes",
    response_model=JobChangeList,
    responses={404: {"model": APIErrorResponse}},
    summary="Inspect persisted field changes",
    description="Ordered by destination version number, field name, then event ID.",
)
async def list_job_changes(
    job_id: UUID,
    request: Request,
    service: JobQueryDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobChangeList | JSONResponse:
    result = await service.changes(job_id, limit=limit, offset=offset)
    return result if result is not None else _job_not_found(request)


@router.get(
    "/{job_id}/lifecycle",
    response_model=JobLifecycleRead,
    responses={404: {"model": APIErrorResponse}},
    summary="Inspect current lifecycle state and historical evidence",
    description=(
        "Events are ordered by occurred_at, created_at, then ID, all ascending. "
        "no_longer_observed_at is OpenRole's confirmation observation time, "
        "rather than an exact employer removal timestamp."
    ),
)
async def get_job_lifecycle(
    job_id: UUID,
    request: Request,
    service: JobQueryDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobLifecycleRead | JSONResponse:
    result = await service.lifecycle(job_id, limit=limit, offset=offset)
    return result if result is not None else _job_not_found(request)
