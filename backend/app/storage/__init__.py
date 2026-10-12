"""Provider-independent object storage infrastructure."""

from app.storage.base import ObjectStorage, StoredObject

__all__ = ["ObjectStorage", "StoredObject"]
