import asyncio
import hashlib
from pathlib import Path

import pytest

from app.storage.base import StoredObject
from app.storage.errors import (
    InvalidObjectKeyError,
    ObjectAlreadyExistsError,
    ObjectNotFoundError,
)
from app.storage.filesystem import FilesystemObjectStorage


@pytest.mark.asyncio
async def test_put_bytes_creates_file_and_returns_metadata(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    storage = FilesystemObjectStorage(root)
    data = b'{"jobs":[]}'

    result = await storage.put_bytes(
        key="bronze/test/jobs.json",
        data=data,
        content_type="application/json",
    )

    assert (root / "bronze/test/jobs.json").read_bytes() == data
    assert result == StoredObject(
        key="bronze/test/jobs.json",
        content_type="application/json",
        content_length_bytes=len(data),
        content_hash=hashlib.sha256(data).hexdigest(),
    )


@pytest.mark.asyncio
async def test_get_bytes_returns_original_data(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    data = b'{"jobs":[{"id":1}]}'
    await storage.put_bytes(
        key="bronze/test/jobs.json",
        data=data,
        content_type="application/json",
    )

    assert await storage.get_bytes(key="bronze/test/jobs.json") == data


@pytest.mark.asyncio
async def test_exists_changes_after_object_is_stored(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    key = "bronze/test/jobs.json"

    assert await storage.exists(key=key) is False

    await storage.put_bytes(key=key, data=b"data", content_type="text/plain")

    assert await storage.exists(key=key) is True


@pytest.mark.asyncio
async def test_existing_object_is_not_overwritten(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    key = "bronze/test/jobs.json"
    await storage.put_bytes(key=key, data=b"original", content_type="text/plain")

    with pytest.raises(ObjectAlreadyExistsError):
        await storage.put_bytes(key=key, data=b"replacement", content_type="text/plain")

    assert await storage.get_bytes(key=key) == b"original"


@pytest.mark.asyncio
async def test_missing_object_raises_stable_error(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)

    with pytest.raises(ObjectNotFoundError):
        await storage.get_bytes(key="bronze/missing.json")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "../outside.json",
        "../../outside.json",
        "/absolute/path.json",
        "C:/Windows/system.json",
        "C:\\Windows\\system.json",
        "bronze\\test\\jobs.json",
        "bronze/./jobs.json",
        "bronze//jobs.json",
    ],
)
async def test_dangerous_object_keys_are_rejected(tmp_path: Path, key: str) -> None:
    root = tmp_path / "objects"
    storage = FilesystemObjectStorage(root)

    with pytest.raises(InvalidObjectKeyError):
        await storage.put_bytes(key=key, data=b"unsafe", content_type="text/plain")

    assert not (tmp_path / "outside.json").exists()


@pytest.mark.asyncio
async def test_key_cannot_escape_through_existing_symlink(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    storage = FilesystemObjectStorage(root)

    with pytest.raises(InvalidObjectKeyError):
        await storage.put_bytes(
            key="escape/object.json",
            data=b"unsafe",
            content_type="application/json",
        )

    assert not (outside / "object.json").exists()


@pytest.mark.asyncio
async def test_nested_directories_are_created_automatically(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    storage = FilesystemObjectStorage(root)
    key = "bronze/greenhouse/source/run/jobs.json"

    await storage.put_bytes(key=key, data=b"nested", content_type="application/json")

    assert (root / key).read_bytes() == b"nested"


@pytest.mark.asyncio
async def test_hash_is_deterministic_for_raw_bytes(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)

    first = await storage.put_bytes(
        key="first.json", data=b"same", content_type="application/json"
    )
    second = await storage.put_bytes(
        key="second.json", data=b"same", content_type="application/json"
    )
    different = await storage.put_bytes(
        key="different.json", data=b"different", content_type="application/json"
    )

    assert first.content_hash == second.content_hash
    assert first.content_hash != different.content_hash
    assert len(first.content_hash) == 64


@pytest.mark.asyncio
async def test_empty_object_is_valid(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)

    result = await storage.put_bytes(
        key="bronze/empty.json",
        data=b"",
        content_type="application/json",
    )

    assert result.content_length_bytes == 0
    assert result.content_hash == hashlib.sha256(b"").hexdigest()
    assert await storage.get_bytes(key="bronze/empty.json") == b""


@pytest.mark.asyncio
async def test_concurrent_writes_publish_only_one_complete_object(
    tmp_path: Path,
) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    key = "bronze/concurrent.json"

    async def attempt(data: bytes) -> StoredObject | ObjectAlreadyExistsError:
        try:
            return await storage.put_bytes(
                key=key,
                data=data,
                content_type="application/json",
            )
        except ObjectAlreadyExistsError as error:
            return error

    results = await asyncio.gather(attempt(b"first"), attempt(b"second"))

    assert sum(isinstance(result, StoredObject) for result in results) == 1
    assert sum(isinstance(result, ObjectAlreadyExistsError) for result in results) == 1
    assert await storage.get_bytes(key=key) in {b"first", b"second"}


@pytest.mark.asyncio
async def test_all_operations_validate_keys(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)

    with pytest.raises(InvalidObjectKeyError):
        await storage.get_bytes(key="../outside.json")

    with pytest.raises(InvalidObjectKeyError):
        await storage.exists(key="../outside.json")
