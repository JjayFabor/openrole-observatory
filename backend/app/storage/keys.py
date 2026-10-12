from pathlib import PurePosixPath, PureWindowsPath

from app.storage.errors import InvalidObjectKeyError


def validate_object_key(key: str) -> tuple[str, ...]:
    """Validate one provider-independent key and return its logical segments."""

    if not key or "\x00" in key or "\\" in key:
        raise InvalidObjectKeyError(f"Invalid object key: {key!r}")

    posix_key = PurePosixPath(key)
    windows_key = PureWindowsPath(key)
    key_parts = tuple(key.split("/"))

    if (
        posix_key.is_absolute()
        or windows_key.is_absolute()
        or bool(windows_key.drive)
        or any(part in {"", ".", ".."} for part in key_parts)
    ):
        raise InvalidObjectKeyError(f"Invalid object key: {key!r}")

    return key_parts
