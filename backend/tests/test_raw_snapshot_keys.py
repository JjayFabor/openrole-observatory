from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.raw_snapshots.keys import build_raw_snapshot_key

SOURCE_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def test_build_raw_snapshot_key_uses_documented_layout() -> None:
    key = build_raw_snapshot_key(
        provider="greenhouse",
        source_connection_id=SOURCE_ID,
        pipeline_run_id=RUN_ID,
        retrieved_at=datetime(2026, 10, 6, 11, tzinfo=UTC),
    )

    assert key == (
        "bronze/greenhouse/11111111-1111-4111-8111-111111111111/"
        "year=2026/month=10/day=06/"
        "run=22222222-2222-4222-8222-222222222222/jobs.json"
    )


def test_build_raw_snapshot_key_partitions_by_utc_date() -> None:
    local_timestamp = datetime(
        2026,
        10,
        7,
        2,
        30,
        tzinfo=timezone(timedelta(hours=8)),
    )

    key = build_raw_snapshot_key(
        provider="greenhouse",
        source_connection_id=SOURCE_ID,
        pipeline_run_id=RUN_ID,
        retrieved_at=local_timestamp,
    )

    assert "/year=2026/month=10/day=06/" in key


def test_build_raw_snapshot_key_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_raw_snapshot_key(
            provider="greenhouse",
            source_connection_id=SOURCE_ID,
            pipeline_run_id=RUN_ID,
            retrieved_at=datetime(2026, 10, 6, 11),
        )


@pytest.mark.parametrize("provider", ["", "Greenhouse", "../greenhouse", "green/house"])
def test_build_raw_snapshot_key_rejects_unsafe_provider_segment(
    provider: str,
) -> None:
    with pytest.raises(ValueError, match="safe lowercase"):
        build_raw_snapshot_key(
            provider=provider,
            source_connection_id=SOURCE_ID,
            pipeline_run_id=RUN_ID,
            retrieved_at=datetime(2026, 10, 6, 11, tzinfo=UTC),
        )
