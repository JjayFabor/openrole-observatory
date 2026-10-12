import logging
from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.api.dependencies import SourceSyncDependency
from app.api.errors import APIErrorResponse, api_error_response
from app.ingestion.errors import SourceSyncFailedError
from app.ingestion.orchestration import (
    DATABASE_WRITE_FAILED,
    PIPELINE_INTERNAL_ERROR,
    RAW_STORAGE_FAILED,
    SOURCE_RESPONSE_INVALID,
)
from app.ingestion.schemas import SourceSyncRead
from app.ingestion.sync import SOURCE_REQUEST_FAILED, SOURCE_REQUEST_TIMEOUT
from app.pipeline_runs.errors import (
    SourceConnectionInactiveError,
    SourceConnectionNotFoundError,
    SourceSyncAlreadyRunningError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["admin-sync"])


@router.post(
    "/sources/{source_id}/sync",
    response_model=SourceSyncRead,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse},
        status.HTTP_409_CONFLICT: {"model": APIErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": APIErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": APIErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": APIErrorResponse},
        status.HTTP_504_GATEWAY_TIMEOUT: {"model": APIErrorResponse},
    },
)
async def sync_source(
    source_id: UUID,
    request: Request,
    service: SourceSyncDependency,
) -> SourceSyncRead | JSONResponse:
    try:
        result = await service.sync_source(source_id)
    except SourceConnectionNotFoundError:
        return api_error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="SOURCE_CONNECTION_NOT_FOUND",
            message="The source connection was not found.",
        )
    except SourceConnectionInactiveError:
        return api_error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="SOURCE_CONNECTION_INACTIVE",
            message="The source connection is inactive.",
        )
    except SourceSyncAlreadyRunningError:
        return api_error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="SOURCE_SYNC_ALREADY_RUNNING",
            message="A synchronization is already running for this source.",
        )
    except SourceSyncFailedError as error:
        return api_error_response(
            request,
            status_code=_sync_failure_status(error.code),
            code=error.code,
            message=error.safe_message,
        )
    except Exception:
        logger.exception(
            "source_sync_http_adapter_failed",
            extra={"source_connection_id": str(source_id)},
        )
        return api_error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=PIPELINE_INTERNAL_ERROR,
            message="Source synchronization could not be completed.",
        )

    return SourceSyncRead.model_validate(result)


def _sync_failure_status(error_code: str) -> int:
    if error_code == SOURCE_REQUEST_TIMEOUT:
        return status.HTTP_504_GATEWAY_TIMEOUT
    if error_code in {SOURCE_REQUEST_FAILED, SOURCE_RESPONSE_INVALID}:
        return status.HTTP_502_BAD_GATEWAY
    if error_code == RAW_STORAGE_FAILED:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if error_code in {DATABASE_WRITE_FAILED, PIPELINE_INTERNAL_ERROR}:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    return status.HTTP_500_INTERNAL_SERVER_ERROR
