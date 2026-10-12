import hashlib

import pytest

from app.source_observations.source_records import (
    build_raw_record_locator,
    compute_source_content_hash,
    serialize_source_record,
)


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, "jobs[0]"), (1, "jobs[1]"), (42, "jobs[42]")],
)
def test_raw_record_locator_uses_array_position(index: int, expected: str) -> None:
    assert build_raw_record_locator(index) == expected


def test_raw_record_locator_rejects_negative_index() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        build_raw_record_locator(-1)


def test_source_record_hash_is_deterministic_across_dict_insertion_order() -> None:
    first = {
        "id": 1001,
        "title": "Développeur Backend",
        "location": {"name": "Montréal"},
    }
    second = {
        "location": {"name": "Montréal"},
        "title": "Développeur Backend",
        "id": 1001,
    }

    assert serialize_source_record(first) == serialize_source_record(second)
    assert compute_source_content_hash(first) == compute_source_content_hash(second)
    assert (
        compute_source_content_hash(first)
        == hashlib.sha256(serialize_source_record(first)).hexdigest()
    )


def test_source_record_hash_changes_with_provider_native_content() -> None:
    baseline = {"id": 1001, "title": "Backend Engineer"}
    changed = {"id": 1001, "title": "Senior Backend Engineer"}

    assert compute_source_content_hash(baseline) != compute_source_content_hash(changed)
