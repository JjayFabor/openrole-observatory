import re
from datetime import UTC, datetime
from uuid import UUID

SAFE_PROVIDER_SEGMENT = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


def build_raw_snapshot_key(
    *,
    provider: str,
    source_connection_id: UUID,
    pipeline_run_id: UUID,
    retrieved_at: datetime,
) -> str:
    """Build one deterministic Bronze key using the retrieval date in UTC."""

    if SAFE_PROVIDER_SEGMENT.fullmatch(provider) is None:
        raise ValueError("provider must be a safe lowercase object-key segment")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")

    retrieved_at_utc = retrieved_at.astimezone(UTC)
    return (
        f"bronze/{provider}/{source_connection_id}/"
        f"year={retrieved_at_utc:%Y}/"
        f"month={retrieved_at_utc:%m}/"
        f"day={retrieved_at_utc:%d}/"
        f"run={pipeline_run_id}/jobs.json"
    )
