from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _is_placeholder(value: str | None) -> bool:
    if value is None or not value.strip():
        return True
    text = value.strip().casefold()
    return (
        "<" in text
        or ">" in text
        or text.startswith(("your_", "replace_", "change_me", "changeme"))
    )


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = Field(repr=False)
    admin_api_token: SecretStr | None = Field(default=None, repr=False)
    object_storage_backend: Literal["filesystem", "r2"] = "filesystem"
    local_storage_path: Path = Path(".local-data")
    r2_endpoint_url: str | None = None
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket_name: str | None = None
    r2_region: str = "auto"
    http_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    http_read_timeout_seconds: float = Field(default=30.0, gt=0)
    # Every counted absence needs run-level evidence; intermediate runs have none.
    job_absence_confirmation_runs: int = Field(default=2, ge=2, le=2)

    @model_validator(mode="after")
    def validate_production_configuration(self) -> Self:
        if self.app_env != "production":
            return self
        self._validate_production_database()
        if "object_storage_backend" not in self.model_fields_set:
            raise ValueError("Production requires explicit OBJECT_STORAGE_BACKEND.")
        if self.object_storage_backend == "filesystem":
            if (
                "local_storage_path" not in self.model_fields_set
                or not self.local_storage_path.is_absolute()
            ):
                raise ValueError(
                    "Production filesystem storage requires explicit absolute "
                    "LOCAL_STORAGE_PATH on persistent storage."
                )
        else:
            self._validate_production_r2()
        token = (
            self.admin_api_token.get_secret_value() if self.admin_api_token else None
        )
        if _is_placeholder(token) or len(token or "") < 32:
            raise ValueError(
                "Production requires ADMIN_API_TOKEN of at least 32 characters."
            )
        return self

    def _validate_production_database(self) -> None:
        try:
            url = make_url(self.database_url)
            valid = (
                url.drivername == "postgresql+asyncpg"
                and bool(url.host)
                and not _is_placeholder(url.database)
                and not _is_placeholder(url.username)
                and not _is_placeholder(url.password)
            )
            if not valid:
                raise ValueError
        except (ArgumentError, ValueError):
            raise ValueError(
                "Production DATABASE_URL must use postgresql+asyncpg with a host, "
                "database, username and non-placeholder password."
            ) from None
        if url.password is not None and url.password.strip().casefold() in {
            "openrole",
            "postgres",
            "password",
            "development",
            "test",
            "change-me",
        }:
            raise ValueError(
                "Production DATABASE_URL must not use known development credentials."
            )

    def _validate_production_r2(self) -> None:
        values = {
            "R2_ENDPOINT_URL": self.r2_endpoint_url,
            "R2_ACCESS_KEY_ID": (
                self.r2_access_key_id.get_secret_value()
                if self.r2_access_key_id
                else None
            ),
            "R2_SECRET_ACCESS_KEY": (
                self.r2_secret_access_key.get_secret_value()
                if self.r2_secret_access_key
                else None
            ),
            "R2_BUCKET_NAME": self.r2_bucket_name,
            "R2_REGION": self.r2_region,
        }
        missing = [name for name, value in values.items() if _is_placeholder(value)]
        if missing:
            raise ValueError(
                "Production requires configured " + ", ".join(missing) + "."
            )
        try:
            endpoint = urlsplit(self.r2_endpoint_url or "")
            valid = (
                endpoint.scheme == "https"
                and bool(endpoint.hostname)
                and bool(
                    (endpoint.hostname or "").removesuffix(".r2.cloudflarestorage.com")
                )
                and (endpoint.hostname or "").endswith(".r2.cloudflarestorage.com")
                and endpoint.port in (None, 443)
                and endpoint.username is None
                and endpoint.password is None
                and endpoint.path in ("", "/")
                and not endpoint.query
                and not endpoint.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                "Production R2_ENDPOINT_URL must be a credential-free HTTPS "
                "Cloudflare R2 S3 endpoint without a path, query or fragment."
            )
        if self.r2_bucket_name == "openrole-development":
            raise ValueError(
                "Production R2_BUCKET_NAME must not use the development bucket."
            )
        if self.r2_region not in {"auto", "us-east-1"}:
            raise ValueError(
                "Production R2_REGION must be auto or its us-east-1 alias."
            )


@lru_cache
def get_settings() -> Settings:
    """Return one settings instance for the lifetime of the process."""

    return Settings()
