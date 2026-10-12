from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

DATABASE = "postgresql+asyncpg://production_user:synthetic-production-credential@database.example/production_db"
R2_SETTINGS: dict[str, object] = {
    "r2_endpoint_url": "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
    "r2_access_key_id": "synthetic-production-access",
    "r2_secret_access_key": "synthetic-production-secret",
    "r2_bucket_name": "openrole-production",
}


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


def production_settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "_env_file": None,
            "app_env": "production",
            "database_url": DATABASE,
            "object_storage_backend": "r2",
            "admin_api_token": "synthetic-administrative-token-32-characters",
            **R2_SETTINGS,
            **overrides,
        }
    )


def test_complete_production_r2_settings_load_without_network_or_secret_repr() -> None:
    settings = production_settings()
    assert settings.object_storage_backend == "r2"
    assert settings.r2_region == "auto"
    assert DATABASE not in repr(settings)
    assert "synthetic-production-credential" not in repr(settings)
    assert "synthetic-production-secret" not in repr(settings)


def test_production_requires_explicit_storage_selection() -> None:
    with pytest.raises(ValidationError, match="explicit OBJECT_STORAGE_BACKEND"):
        Settings(_env_file=None, app_env="production", database_url=DATABASE)


def test_production_filesystem_requires_explicit_path() -> None:
    with pytest.raises(ValidationError, match="LOCAL_STORAGE_PATH"):
        production_settings(object_storage_backend="filesystem")


@pytest.mark.parametrize("path", ["", ".local-data", "relative/raw", "~/raw"])
def test_production_filesystem_rejects_relative_paths(path: str) -> None:
    with pytest.raises(ValidationError, match="absolute LOCAL_STORAGE_PATH"):
        production_settings(
            object_storage_backend="filesystem", local_storage_path=path
        )


def test_explicit_production_filesystem_accepts_absolute_path_and_unused_r2_blanks(
    tmp_path: Path,
) -> None:
    settings = production_settings(
        object_storage_backend="filesystem",
        local_storage_path=tmp_path,
        r2_endpoint_url="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_bucket_name="",
    )
    assert settings.local_storage_path == tmp_path


@pytest.mark.parametrize(
    "field, name",
    [
        ("r2_endpoint_url", "R2_ENDPOINT_URL"),
        ("r2_access_key_id", "R2_ACCESS_KEY_ID"),
        ("r2_secret_access_key", "R2_SECRET_ACCESS_KEY"),
        ("r2_bucket_name", "R2_BUCKET_NAME"),
        ("r2_region", "R2_REGION"),
    ],
)
@pytest.mark.parametrize("value", ["", "   ", "REPLACE_ME", "<placeholder>"])
def test_production_r2_rejects_unfilled_fields(
    field: str, name: str, value: str
) -> None:
    with pytest.raises(ValidationError, match=name):
        production_settings(**{field: value})


@pytest.mark.parametrize(
    "field",
    ["r2_endpoint_url", "r2_access_key_id", "r2_secret_access_key", "r2_bucket_name"],
)
def test_production_r2_rejects_missing_required_fields(field: str) -> None:
    data = dict(R2_SETTINGS)
    data.pop(field)
    with pytest.raises(ValidationError, match=field.upper()):
        Settings.model_validate(
            {
                "_env_file": None,
                "app_env": "production",
                "database_url": DATABASE,
                "object_storage_backend": "r2",
                "admin_api_token": "synthetic-administrative-token-32-characters",
                **data,
            }
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://account.r2.cloudflarestorage.com",
        "https://example.test",
        "https://.r2.cloudflarestorage.com",
        "https://account.r2.cloudflarestorage.com.evil.test",
        "https://private-user:private-password@account.r2.cloudflarestorage.com",
        "https://account.r2.cloudflarestorage.com/bucket",
        "https://account.r2.cloudflarestorage.com?secret=value",
        "https://account.r2.cloudflarestorage.com#fragment",
        "https://account.r2.cloudflarestorage.com:1234",
        "https://account.r2.cloudflarestorage.com:invalid",
    ],
)
def test_production_r2_rejects_unsafe_endpoints(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="R2_ENDPOINT_URL"):
        production_settings(r2_endpoint_url=endpoint)


def test_production_rejects_development_bucket_and_unsupported_region() -> None:
    with pytest.raises(ValidationError, match="development bucket"):
        production_settings(r2_bucket_name="openrole-development")
    with pytest.raises(ValidationError, match="R2_REGION"):
        production_settings(r2_region="eu")
    assert production_settings(r2_region="us-east-1").r2_region == "us-east-1"
    assert (
        production_settings(
            r2_endpoint_url="https://account.eu.r2.cloudflarestorage.com"
        ).r2_region
        == "auto"
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "sqlite:///development.db",
        "postgresql://user:secret@database.example/db",
        "postgresql+asyncpg:///db",
        "postgresql+asyncpg://user@database.example/db",
        "postgresql+asyncpg://user:secret@database.example",
        "postgresql+asyncpg://user:REPLACE_ME@database.example/db",
        "postgresql+asyncpg://user:secret@database.example:invalid/db",
    ],
)
def test_production_database_requires_usable_postgresql_configuration(url: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        production_settings(database_url=url)


@pytest.mark.parametrize(
    "password", ["openrole", "postgres", "password", "development", "test", "change-me"]
)
def test_production_database_rejects_known_development_credentials(
    password: str,
) -> None:
    with pytest.raises(ValidationError, match="development credentials"):
        production_settings(
            database_url=f"postgresql+asyncpg://user:{password}@localhost:5434/db"
        )


def test_production_validation_errors_do_not_print_settings_inputs_or_credentials() -> (
    None
):
    with pytest.raises(ValidationError) as error:
        production_settings(
            r2_endpoint_url="https://private-user:private-password@example.test"
        )
    text = str(error.value)
    assert "R2_ENDPOINT_URL" in text
    for secret in [
        DATABASE,
        "synthetic-production-secret",
        "synthetic-production-credential",
        "private-password",
    ]:
        assert secret not in text


def test_production_rules_apply_to_environment_and_dotenv_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f"APP_ENV=production\nDATABASE_URL={DATABASE}\nOBJECT_STORAGE_BACKEND=filesystem\nLOCAL_STORAGE_PATH=.local-data\n"
    )
    with pytest.raises(ValidationError, match="LOCAL_STORAGE_PATH"):
        Settings(_env_file=dotenv)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "persistent-raw"))
    monkeypatch.setenv(
        "ADMIN_API_TOKEN", "synthetic-administrative-token-32-characters"
    )
    assert Settings(_env_file=dotenv).local_storage_path == tmp_path / "persistent-raw"


@pytest.mark.parametrize("environment", ["development", "test"])
def test_development_and_test_keep_existing_filesystem_defaults(
    environment: str,
) -> None:
    settings = Settings.model_validate(
        {
            "_env_file": None,
            "app_env": environment,
            "database_url": "postgresql+asyncpg://openrole:openrole@localhost/openrole",
        }
    )
    assert settings.object_storage_backend == "filesystem"
    assert settings.local_storage_path == Path(".local-data")
