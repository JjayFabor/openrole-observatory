import hashlib
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.storage.base import StoredObject
from app.storage.errors import (
    InvalidObjectKeyError,
    ObjectAlreadyExistsError,
    ObjectNotFoundError,
    StorageReadError,
    StorageWriteError,
)
from app.storage.r2 import R2ObjectStorage


def client_error(
    *, code: str, status: int, message: str = "provider failure"
) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "test-operation",
    )


@pytest.mark.asyncio
async def test_exists_returns_true_when_head_succeeds() -> None:
    client = MagicMock()
    client.head_object.return_value = {}
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    assert await storage.exists(key="bronze/test/jobs.json") is True
    client.head_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="bronze/test/jobs.json",
    )


@pytest.mark.asyncio
async def test_exists_returns_false_only_for_not_found() -> None:
    client = MagicMock()
    client.head_object.side_effect = client_error(code="NotFound", status=404)
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    assert await storage.exists(key="bronze/missing.json") is False


@pytest.mark.asyncio
async def test_exists_maps_forbidden_to_storage_read_error() -> None:
    client = MagicMock()
    client.head_object.side_effect = client_error(code="AccessDenied", status=403)
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    with pytest.raises(StorageReadError):
        await storage.exists(key="bronze/private.json")


@pytest.mark.asyncio
async def test_get_bytes_returns_remote_body() -> None:
    client = MagicMock()
    client.get_object.return_value = {"Body": BytesIO(b'{"jobs":[]}')}
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    result = await storage.get_bytes(key="bronze/test/jobs.json")

    assert result == b'{"jobs":[]}'
    client.get_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="bronze/test/jobs.json",
    )


@pytest.mark.asyncio
async def test_get_bytes_maps_missing_object() -> None:
    client = MagicMock()
    client.get_object.side_effect = client_error(code="NoSuchKey", status=404)
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    with pytest.raises(ObjectNotFoundError):
        await storage.get_bytes(key="bronze/missing.json")


@pytest.mark.asyncio
async def test_put_bytes_uses_atomic_conditional_creation() -> None:
    client = MagicMock()
    client.put_object.return_value = {}
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")
    data = b'{"jobs":[]}'

    result = await storage.put_bytes(
        key="bronze/test/jobs.json",
        data=data,
        content_type="application/json",
    )

    assert result == StoredObject(
        key="bronze/test/jobs.json",
        content_type="application/json",
        content_length_bytes=len(data),
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="bronze/test/jobs.json",
        Body=data,
        ContentType="application/json",
        IfNoneMatch="*",
    )


@pytest.mark.asyncio
async def test_put_bytes_maps_failed_precondition_to_existing_object() -> None:
    client = MagicMock()
    client.put_object.side_effect = client_error(
        code="PreconditionFailed",
        status=412,
    )
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    with pytest.raises(ObjectAlreadyExistsError):
        await storage.put_bytes(
            key="bronze/existing.json",
            data=b"replacement",
            content_type="application/json",
        )


@pytest.mark.asyncio
async def test_provider_error_does_not_expose_credentials() -> None:
    client = MagicMock()
    secret = "very-secret-r2-credential"
    client.put_object.side_effect = client_error(
        code="AccessDenied",
        status=403,
        message=f"Credential {secret} is invalid",
    )
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    with pytest.raises(StorageWriteError) as error_info:
        await storage.put_bytes(
            key="bronze/test.json",
            data=b"data",
            content_type="application/json",
        )

    assert secret not in str(error_info.value)
    assert error_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_r2_reuses_provider_independent_key_validation() -> None:
    client = MagicMock()
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    with pytest.raises(InvalidObjectKeyError):
        await storage.exists(key="../../outside.json")

    client.head_object.assert_not_called()


@pytest.mark.asyncio
async def test_get_bytes_rejects_missing_response_body() -> None:
    client = MagicMock()
    client.get_object.return_value = {}
    storage = R2ObjectStorage(client=client, bucket_name="test-bucket")

    with pytest.raises(StorageReadError):
        await storage.get_bytes(key="bronze/test.json")
