class StorageError(Exception):
    """Base class for provider-independent object storage failures."""


class StorageConfigurationError(StorageError):
    """Raised when the selected storage provider is not configured safely."""


class InvalidObjectKeyError(StorageError):
    """Raised when an object key cannot be mapped safely beneath storage."""


class ObjectAlreadyExistsError(StorageError):
    """Raised when an immutable object already exists at the requested key."""


class ObjectNotFoundError(StorageError):
    """Raised when a requested object does not exist."""


class StorageReadError(StorageError):
    """Raised when an existing object cannot be inspected or read."""


class StorageWriteError(StorageError):
    """Raised when object bytes cannot be written safely."""
