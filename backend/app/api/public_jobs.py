import logging
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import PublicJobQueryDependency
from app.api.errors import APIErrorResponse, api_error_response
from app.jobs.errors import (
    CurrentJobVersionInvariantError,
    CurrentJobVersionMissingError,
)
from app.jobs.public_change_schemas import PublicJobChangesResponse
from app.jobs.public_errors import PublicJobReadError
from app.jobs.public_read_schemas import (
    PublicEmploymentFilter,
    PublicJobDetail,
    PublicJobListResponse,
    PublicJobSitemapResponse,
    PublicWorkplaceFilter,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/public/jobs", tags=["public-jobs"])
_read_errors = (
    CurrentJobVersionMissingError,
    CurrentJobVersionInvariantError,
    PublicJobReadError,
)


def _unavailable(request: Request, error: Exception) -> JSONResponse:
    logger.error(
        "public_job_read_invariant_failed", extra={"error_type": type(error).__name__}
    )
    return api_error_response(
        request,
        status_code=500,
        code="PUBLIC_JOBS_UNAVAILABLE",
        message="Job listings are temporarily unavailable.",
    )


@router.get(
    "",
    response_model=PublicJobListResponse,
    responses={500: {"model": APIErrorResponse}},
    summary="Discover currently observed listings from employer ATS sources",
    description=(
        "Includes observed jobs from active sources with one current canonical "
        "version. Ordered by last_seen_at descending, then job ID ascending. "
        "q matches literal text case-insensitively in title, company name or "
        "location_text; location searches location_text. Filters intersect. "
        "Observation is evidence of a listing, not confirmation of hiring."
    ),
)
async def list_public_jobs(
    request: Request,
    service: PublicJobQueryDependency,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2_147_483_647),
    q: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    workplace_type: PublicWorkplaceFilter | None = None,
    employment_type: PublicEmploymentFilter | None = None,
) -> PublicJobListResponse | JSONResponse:
    try:
        return await service.list(
            limit=limit,
            offset=offset,
            q=q,
            location=location,
            workplace_type=workplace_type,
            employment_type=employment_type,
        )
    except _read_errors as error:
        return _unavailable(request, error)


@router.get(
    "/sitemap",
    response_model=PublicJobSitemapResponse,
    responses={500: {"model": APIErrorResponse}},
    summary="List sitemap-eligible public IDs in stable bounded batches",
    description=(
        "Observed jobs from active sources with one current version. UUID ordering "
        "is independent of changing observation times. next_after is null on the "
        "last batch. Contains no descriptions, history or operational fields."
    ),
)
async def list_public_sitemap_jobs(
    request: Request,
    service: PublicJobQueryDependency,
    limit: int = Query(default=1000, ge=1, le=1000),
    after: UUID | None = None,
) -> PublicJobSitemapResponse | JSONResponse:
    try:
        return await service.sitemap(limit=limit, after=after)
    except _read_errors as error:
        return _unavailable(request, error)


@router.get(
    "/{job_id}",
    response_model=PublicJobDetail,
    responses={404: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}},
    summary="Read a current canonical listing and factual observation timestamps",
    description=(
        "Known not-observed jobs and jobs from inactive sources remain addressable. "
        "no_longer_observed_at records OpenRole's confirmation time, not the "
        "employer's closure time. Description HTML is stored source content and "
        "must be sanitized before rendering."
    ),
)
async def get_public_job(
    job_id: UUID, request: Request, service: PublicJobQueryDependency
) -> PublicJobDetail | JSONResponse:
    try:
        result = await service.get(job_id)
    except _read_errors as error:
        return _unavailable(request, error)
    if result is None:
        return api_error_response(
            request,
            status_code=404,
            code="JOB_NOT_FOUND",
            message="The job was not found.",
        )
    return result


@router.get(
    "/{job_id}/changes",
    response_model=PublicJobChangesResponse,
    responses={404: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}},
    summary="Read recent material listing changes without operational provenance",
    description=(
        "Returns complete curated transition groups, newest observation first. "
        "limit counts groups (default 10, maximum 50). Historical and inactive-source "
        "jobs remain addressable. Description changes are markers only; metadata "
        "and source URL churn are excluded. observed_at is OpenRole's observation "
        "time, not the exact time of an employer action."
    ),
)
async def get_public_job_changes(
    job_id: UUID,
    request: Request,
    service: PublicJobQueryDependency,
    limit: int = Query(default=10, ge=1, le=50),
) -> PublicJobChangesResponse | JSONResponse:
    try:
        result = await service.changes(job_id, limit=limit)
    except PublicJobReadError as error:
        return _unavailable(request, error)
    if result is None:
        return api_error_response(
            request,
            status_code=404,
            code="JOB_NOT_FOUND",
            message="The job was not found.",
        )
    return result
