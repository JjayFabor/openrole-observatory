import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

from app.storage.base import StoredObject
from app.storage.errors import (
    InvalidObjectKeyError,
    ObjectAlreadyExistsError,
    ObjectNotFoundError,
    StorageReadError,
    StorageWriteError,
)
from app.storage.keys import validate_object_key


class FilesystemObjectStorage:
    """Store immutable objects as files beneath one configured root."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve(strict=False)

    async def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        return await asyncio.to_thread(
            self._put_bytes,
            key,
            data,
            content_type,
        )

    async def get_bytes(self, *, key: str) -> bytes:
        return await asyncio.to_thread(self._get_bytes, key)

    async def exists(self, *, key: str) -> bool:
        return await asyncio.to_thread(self._exists, key)

    def _put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        target = self._path_for_key(key)
        temporary_path: Path | None = None

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target = self._path_for_key(key)

            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=".openrole-",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)

            with os.fdopen(file_descriptor, "wb") as temporary_file:
                temporary_file.write(data)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            try:
                os.link(temporary_path, target)
            except FileExistsError as error:
                raise ObjectAlreadyExistsError(
                    f"Object already exists for key: {key}"
                ) from error

            return StoredObject(
                key=key,
                content_type=content_type,
                content_length_bytes=len(data),
                content_hash=hashlib.sha256(data).hexdigest(),
            )
        except ObjectAlreadyExistsError:
            raise
        except OSError as error:
            raise StorageWriteError(f"Could not store object for key: {key}") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _get_bytes(self, key: str) -> bytes:
        target = self._path_for_key(key)

        try:
            return target.read_bytes()
        except FileNotFoundError as error:
            raise ObjectNotFoundError(f"Object not found for key: {key}") from error
        except OSError as error:
            raise StorageReadError(f"Could not read object for key: {key}") from error

    def _exists(self, key: str) -> bool:
        target = self._path_for_key(key)

        try:
            return target.is_file()
        except OSError as error:
            raise StorageReadError(
                f"Could not inspect object for key: {key}"
            ) from error

    def _path_for_key(self, key: str) -> Path:
        key_parts = validate_object_key(key)
        target = self._root.joinpath(*key_parts).resolve(strict=False)

        try:
            target.relative_to(self._root)
        except ValueError as error:
            raise InvalidObjectKeyError(f"Invalid object key: {key!r}") from error

        return target
