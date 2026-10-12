from typing import cast

import boto3  # type: ignore[import-untyped]

from app.config import PROJECT_ROOT, Settings
from app.storage.base import ObjectStorage
from app.storage.errors import StorageConfigurationError
from app.storage.filesystem import FilesystemObjectStorage
from app.storage.r2 import R2ObjectStorage, S3Client


def create_object_storage(settings: Settings) -> ObjectStorage:
    """Build the configured object-storage adapter without global state."""

    if settings.object_storage_backend == "filesystem":
        storage_root = settings.local_storage_path
        if not storage_root.is_absolute():
            storage_root = PROJECT_ROOT / storage_root
        return FilesystemObjectStorage(storage_root)

    if settings.object_storage_backend == "r2":
        endpoint_url, access_key_id, secret_access_key, bucket_name, region = (
            _validated_r2_configuration(settings)
        )
        client = cast(
            S3Client,
            boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
            ),
        )
        return R2ObjectStorage(client=client, bucket_name=bucket_name)

    raise StorageConfigurationError(
        f"Unsupported object storage backend: {settings.object_storage_backend}"
    )


def _validated_r2_configuration(
    settings: Settings,
) -> tuple[str, str, str, str, str]:
    access_key_id = (
        settings.r2_access_key_id.get_secret_value()
        if settings.r2_access_key_id is not None
        else None
    )
    secret_access_key = (
        settings.r2_secret_access_key.get_secret_value()
        if settings.r2_secret_access_key is not None
        else None
    )
    values = {
        "R2_ENDPOINT_URL": settings.r2_endpoint_url,
        "R2_ACCESS_KEY_ID": access_key_id,
        "R2_SECRET_ACCESS_KEY": secret_access_key,
        "R2_BUCKET_NAME": settings.r2_bucket_name,
        "R2_REGION": settings.r2_region,
    }
    missing = [name for name, value in values.items() if not value or not value.strip()]

    if missing:
        raise StorageConfigurationError(
            f"Missing required R2 configuration: {', '.join(missing)}"
        )

    return (
        cast(str, settings.r2_endpoint_url).strip(),
        cast(str, access_key_id).strip(),
        cast(str, secret_access_key).strip(),
        cast(str, settings.r2_bucket_name).strip(),
        settings.r2_region.strip(),
    )
