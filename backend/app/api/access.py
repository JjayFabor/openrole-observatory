from secrets import compare_digest
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings

bearer = HTTPBearer(auto_error=False)


def require_admin_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    """Protect operational routes independently of frontend access checks."""
    settings = cast(Settings, request.app.state.settings)
    expected = settings.admin_api_token
    if expected is None and settings.app_env != "production":
        return
    if (
        expected is not None
        and credentials is not None
        and compare_digest(
            credentials.credentials.encode("utf-8"),
            expected.get_secret_value().encode("utf-8"),
        )
    ):
        return
    raise HTTPException(
        status_code=401,
        detail="Administrative access requires a valid bearer token.",
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )
