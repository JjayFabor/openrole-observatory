from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.storage.errors import StorageConfigurationError
from app.storage.factory import create_object_storage
from app.storage.filesystem import FilesystemObjectStorage
from app.storage.r2 import R2ObjectStorage


def test_factory_creates_configured_filesystem_storage(tmp_path: Path) -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole",
        object_storage_backend="filesystem",
        local_storage_path=tmp_path,
        _env_file=None,
    )

    storage = create_object_storage(settings)

    assert isinstance(storage, FilesystemObjectStorage)


def test_factory_creates_configured_r2_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr("app.storage.factory.boto3.client", client_factory)
    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole",
        object_storage_backend="r2",
        r2_endpoint_url="https://example-account.r2.cloudflarestorage.com",
        r2_access_key_id=SecretStr("test-access-key"),
        r2_secret_access_key=SecretStr("test-secret-key"),
        r2_bucket_name="test-bucket",
        _env_file=None,
    )

    storage = create_object_storage(settings)

    assert isinstance(storage, R2ObjectStorage)
    client_factory.assert_called_once_with(
        "s3",
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
        region_name="auto",
    )


def test_factory_rejects_incomplete_r2_configuration() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://database.example/openrole",
        object_storage_backend="r2",
        _env_file=None,
    )

    with pytest.raises(
        StorageConfigurationError,
        match="R2_ENDPOINT_URL.*R2_ACCESS_KEY_ID.*R2_SECRET_ACCESS_KEY.*R2_BUCKET_NAME",
    ):
        create_object_storage(settings)


def test_settings_reject_unsupported_storage_provider() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://database.example/openrole",
                "object_storage_backend": "unsupported",
            }
        )
