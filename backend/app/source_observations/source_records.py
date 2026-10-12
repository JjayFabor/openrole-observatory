import hashlib
import json
from collections.abc import Mapping


def build_raw_record_locator(index: int) -> str:
    if index < 0:
        raise ValueError("source record index must not be negative")
    return f"jobs[{index}]"


def serialize_source_record(raw_record: Mapping[str, object]) -> bytes:
    """Serialize one decoded provider record deterministically for hashing."""

    serialized = json.dumps(
        dict(raw_record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return serialized.encode("utf-8")


def compute_source_content_hash(raw_record: Mapping[str, object]) -> str:
    return hashlib.sha256(serialize_source_record(raw_record)).hexdigest()
