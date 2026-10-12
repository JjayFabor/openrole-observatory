from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Provider-independent metadata returned after storing object bytes."""

    key: str
    content_type: str
    content_length_bytes: int
    content_hash: str


class ObjectStorage(Protocol):
    """Operations application services may perform on immutable objects."""

    async def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject: ...

    async def get_bytes(self, *, key: str) -> bytes: ...

    async def exists(self, *, key: str) -> bool: ...
