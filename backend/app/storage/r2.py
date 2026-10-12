import asyncio
import hashlib
from collections.abc import Mapping
from typing import Protocol, cast

from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
)

from app.storage.base import StoredObject
from app.storage.errors import (
    ObjectAlreadyExistsError,
    ObjectNotFoundError,
    StorageReadError,
    StorageWriteError,
)
from app.storage.keys import validate_object_key


class S3Client(Protocol):
    """The small boto3 client surface used by this adapter and its tests."""

    def put_object(self, **kwargs: object) -> object: ...

    def get_object(self, **kwargs: object) -> dict[str, object]: ...

    def head_object(self, **kwargs: object) -> object: ...

    def delete_object(self, **kwargs: object) -> object: ...


class R2ObjectStorage:
    """Store immutable objects through Cloudflare R2's S3-compatible API."""

    def __init__(self, *, client: S3Client, bucket_name: str) -> None:
        self._client = client
        self._bucket_name = bucket_name

    async def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        validate_object_key(key)
        content_hash = hashlib.sha256(data).hexdigest()

        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
                IfNoneMatch="*",
            )
        except ClientError as error:
            if _matches_client_error(
                error,
                codes={"PreconditionFailed", "412"},
                statuses={412},
            ):
                raise ObjectAlreadyExistsError(
                    f"Object already exists for key: {key}"
                ) from None
            raise StorageWriteError(f"Could not store object for key: {key}") from None
        except BotoCoreError:
            raise StorageWriteError(f"Could not store object for key: {key}") from None

        return StoredObject(
            key=key,
            content_type=content_type,
            content_length_bytes=len(data),
            content_hash=content_hash,
        )

    async def get_bytes(self, *, key: str) -> bytes:
        validate_object_key(key)

        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=self._bucket_name,
                Key=key,
            )
        except ClientError as error:
            if _is_not_found(error):
                raise ObjectNotFoundError(f"Object not found for key: {key}") from None
            raise StorageReadError(f"Could not read object for key: {key}") from None
        except BotoCoreError:
            raise StorageReadError(f"Could not read object for key: {key}") from None

        body = response.get("Body")
        read = getattr(body, "read", None)
        if not callable(read):
            raise StorageReadError(f"Could not read object for key: {key}")

        try:
            data = await asyncio.to_thread(read)
        except (BotoCoreError, OSError):
            raise StorageReadError(f"Could not read object for key: {key}") from None

        if not isinstance(data, bytes):
            raise StorageReadError(f"Could not read object for key: {key}")

        return data

    async def exists(self, *, key: str) -> bool:
        validate_object_key(key)

        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket_name,
                Key=key,
            )
        except ClientError as error:
            if _is_not_found(error):
                return False
            raise StorageReadError(f"Could not inspect object for key: {key}") from None
        except BotoCoreError:
            raise StorageReadError(f"Could not inspect object for key: {key}") from None

        return True


def _is_not_found(error: ClientError) -> bool:
    return _matches_client_error(
        error,
        codes={"404", "NoSuchKey", "NotFound"},
        statuses={404},
    )


def _matches_client_error(
    error: ClientError,
    *,
    codes: set[str],
    statuses: set[int],
) -> bool:
    response = cast(Mapping[str, object], error.response)
    error_details = response.get("Error")
    response_metadata = response.get("ResponseMetadata")

    code: str | None = None
    status: int | None = None

    if isinstance(error_details, Mapping):
        raw_code = error_details.get("Code")
        if raw_code is not None:
            code = str(raw_code)

    if isinstance(response_metadata, Mapping):
        raw_status = response_metadata.get("HTTPStatusCode")
        if isinstance(raw_status, int):
            status = raw_status

    return code in codes or status in statuses
