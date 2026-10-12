from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.dependencies import get_public_job_query_service, get_source_query_service
from app.config import Settings
from app.main import create_app

TOKEN = "synthetic-administrative-token-32-characters"
ID = "11111111-1111-4111-8111-111111111111"


def access_client(*, token: str | None = TOKEN, production: bool = False) -> TestClient:
    settings = Settings(
        _env_file=None,
        app_env="production" if production else "test",
        database_url="postgresql+asyncpg://operator:synthetic-db-credential@localhost:1/db",
        object_storage_backend="filesystem",
        local_storage_path=Path("/tmp/openrole-access-tests"),
        admin_api_token=SecretStr(token) if token is not None else None,
    )
    return TestClient(create_app(settings))


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/jobs"),
        ("GET", f"/api/v1/jobs/{ID}"),
        ("GET", f"/api/v1/jobs/{ID}/versions"),
        ("GET", f"/api/v1/jobs/{ID}/changes"),
        ("GET", f"/api/v1/jobs/{ID}/lifecycle"),
        ("GET", "/api/v1/sources"),
        ("GET", f"/api/v1/sources/{ID}"),
        ("GET", "/api/v1/pipeline-runs"),
        ("GET", f"/api/v1/pipeline-runs/{ID}"),
        ("GET", "/api/v1/quarantine"),
        ("GET", f"/api/v1/quarantine/{ID}"),
        ("POST", f"/api/v1/sources/{ID}/sync"),
    ],
)
def test_operational_routes_reject_anonymous_requests_before_services(
    method: str, path: str
) -> None:
    with access_client(production=True) as client:
        response = client.request(method, path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"
    assert TOKEN not in response.text


@pytest.mark.parametrize(
    "authorization", ["Bearer wrong", "Basic dXNlcjpwYXNz", "Bearer", "Bearer café"]
)
def test_wrong_and_malformed_credentials_are_rejected(authorization: str) -> None:
    with access_client() as client:
        # ASGI can carry non-ASCII header bytes; HTTPX strings enforce ASCII.
        response = client.get(
            "/api/v1/sources", headers={b"authorization": authorization.encode("utf-8")}
        )
    assert response.status_code == 401


@pytest.mark.parametrize("token", [None, TOKEN])
def test_correct_token_and_unconfigured_local_mode_reach_existing_handler(
    token: str | None,
) -> None:
    client = access_client(token=token)
    service = AsyncMock()
    service.list.return_value = {"items": [], "total": 0, "limit": 25, "offset": 0}
    cast(FastAPI, client.app).dependency_overrides[get_source_query_service] = lambda: (
        service
    )
    with client:
        response = client.get(
            "/api/v1/sources",
            headers={"Authorization": f"Bearer {TOKEN}"} if token else {},
        )
    assert response.status_code == 200
    service.list.assert_awaited_once()


def test_public_reads_and_health_do_not_require_admin_credentials() -> None:
    client = access_client(production=True)
    service = AsyncMock()
    service.list.return_value = {"items": [], "total": 0, "limit": 25, "offset": 0}
    cast(FastAPI, client.app).dependency_overrides[get_public_job_query_service] = (
        lambda: service
    )
    with client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.get("/api/v1/public/jobs").status_code == 200
        for path in ["/docs", "/redoc", "/openapi.json"]:
            assert client.get(path).status_code == 404


@pytest.mark.parametrize("token", [None, "", "short", "REPLACE_ME" * 4])
def test_production_requires_non_placeholder_admin_token(token: str | None) -> None:
    with pytest.raises(ValueError, match="ADMIN_API_TOKEN") as error:
        access_client(token=token, production=True)
    assert "synthetic-db-credential" not in str(error.value)
