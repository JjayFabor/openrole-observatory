from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class APIErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class APIErrorResponse(BaseModel):
    error: APIErrorDetail


def api_error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID")
    body = APIErrorResponse(
        error=APIErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())
