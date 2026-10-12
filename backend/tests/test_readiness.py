from fastapi.testclient import TestClient

from app.config import Settings
from app.database.health import get_database_readiness
from app.main import app, create_app


def test_ready_when_database_is_available() -> None:
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "available"}


def test_not_ready_response_does_not_expose_database_error() -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://127.0.0.1:1/openrole",
        _env_file=None,
    )
    test_app = create_app(settings)

    async def database_is_unavailable() -> bool:
        return False

    test_app.dependency_overrides[get_database_readiness] = database_is_unavailable

    with TestClient(test_app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }
    assert "127.0.0.1" not in response.text
