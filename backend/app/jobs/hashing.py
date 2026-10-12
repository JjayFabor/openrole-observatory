import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import JsonValue

from app.jobs.schemas import CanonicalJobInput

_UNORDERED_METADATA_COLLECTIONS = frozenset({"departments", "offices"})


def build_canonical_job_hash_payload(job: CanonicalJobInput) -> dict[str, object]:
    """Select the canonical fields that define material job content."""

    return {
        "title": job.title,
        "description": job.description,
        "location_text": job.location_text,
        "city": job.city,
        "region": job.region,
        "country_code": job.country_code,
        "workplace_type": job.workplace_type,
        "employment_type": job.employment_type,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "source_url": str(job.source_url),
        "canonical_metadata": job.canonical_metadata,
    }


def serialize_canonical_job_hash_payload(job: CanonicalJobInput) -> bytes:
    """Serialize material job content into deterministic UTF-8 JSON bytes."""

    normalized = normalize_canonical_job_values(build_canonical_job_hash_payload(job))
    return _dump_json(normalized).encode("utf-8")


def normalize_canonical_job_values(
    values: Mapping[str, object],
) -> dict[str, JsonValue]:
    """Copy job material values into the shared hash/diff JSON representation."""

    normalized = _normalize_json_value(values)
    if not isinstance(normalized, dict):
        raise TypeError("Canonical job hash payload must be a dictionary.")

    metadata = normalized.get("canonical_metadata")
    if isinstance(metadata, dict):
        _sort_unordered_metadata_collections(metadata)

    return normalized


def compute_canonical_job_hash(job: CanonicalJobInput) -> str:
    """Return the SHA-256 digest of a canonical job's material content."""

    payload_bytes = serialize_canonical_job_hash_payload(job)
    return hashlib.sha256(payload_bytes).hexdigest()


def _normalize_json_value(value: object) -> JsonValue:
    if isinstance(value, Enum):
        return _normalize_json_value(value.value)

    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Canonical hash datetimes must be timezone-aware.")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Canonical hash Decimal values must be finite.")
        if value.is_zero():
            return "0"
        return format(value.normalize(), "f")

    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical hash float values must be finite.")
        return value

    if isinstance(value, Mapping):
        normalized_mapping: dict[str, JsonValue] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError("Canonical hash dictionary keys must be strings.")
            normalized_mapping[key] = _normalize_json_value(nested_value)
        return normalized_mapping

    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]

    raise TypeError(f"Unsupported canonical hash value: {type(value).__name__}.")


def _sort_unordered_metadata_collections(metadata: dict[str, JsonValue]) -> None:
    for field_name in _UNORDERED_METADATA_COLLECTIONS:
        collection = metadata.get(field_name)
        if isinstance(collection, list):
            metadata[field_name] = sorted(collection, key=_dump_json)


def _dump_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
