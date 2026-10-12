from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.config import Settings


def test_database_url_loads_from_environment(monkeypatch: MonkeyPatch) -> None:
    database_url = "postgresql+asyncpg://database.example/openrole"
    monkeypatch.setenv("DATABASE_URL", database_url)

    settings = Settings(_env_file=None)

    assert settings.database_url == database_url


def test_local_storage_path_loads_from_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_STORAGE_PATH", "custom-local-data")

    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole",
        _env_file=None,
    )

    assert settings.local_storage_path == Path("custom-local-data")


def test_r2_configuration_loads_without_exposing_secret_values(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "R2_ENDPOINT_URL",
        "https://example-account.r2.cloudflarestorage.com",
    )
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret-key")
    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")

    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole",
        _env_file=None,
    )

    assert settings.r2_endpoint_url == (
        "https://example-account.r2.cloudflarestorage.com"
    )
    assert settings.r2_access_key_id is not None
    assert settings.r2_access_key_id.get_secret_value() == "test-access-key"
    assert settings.r2_secret_access_key is not None
    assert settings.r2_secret_access_key.get_secret_value() == "test-secret-key"
    assert "test-secret-key" not in repr(settings)
    assert settings.r2_bucket_name == "test-bucket"
    assert settings.r2_region == "auto"


def test_http_timeouts_load_as_positive_seconds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_CONNECT_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("HTTP_READ_TIMEOUT_SECONDS", "15")

    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole",
        _env_file=None,
    )

    assert settings.http_connect_timeout_seconds == 2.5
    assert settings.http_read_timeout_seconds == 15.0


def test_absence_confirmation_defaults_to_two(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_ABSENCE_CONFIRMATION_RUNS", raising=False)

    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole", _env_file=None
    )

    assert settings.job_absence_confirmation_runs == 2


def test_absence_confirmation_threshold_loads_from_environment(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOB_ABSENCE_CONFIRMATION_RUNS", "2")

    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole", _env_file=None
    )

    assert settings.job_absence_confirmation_runs == 2


@pytest.mark.parametrize("threshold", ["-1", "0", "1", "3", "10", "2.5", "invalid"])
def test_unsupported_absence_confirmation_threshold_fails_clearly(
    monkeypatch: MonkeyPatch, threshold: str
) -> None:
    monkeypatch.setenv("JOB_ABSENCE_CONFIRMATION_RUNS", threshold)

    with pytest.raises(ValidationError, match="job_absence_confirmation_runs"):
        Settings(
            database_url="postgresql+asyncpg://database.example/openrole",
            _env_file=None,
        )
