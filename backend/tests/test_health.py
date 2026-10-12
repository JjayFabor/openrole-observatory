from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def create_app_without_database() -> TestClient:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://127.0.0.1:1/openrole",
        _env_file=None,
    )
    return TestClient(create_app(settings))


def test_application_starts() -> None:
    with create_app_without_database():
        pass


def test_health_endpoint() -> None:
    with create_app_without_database() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
