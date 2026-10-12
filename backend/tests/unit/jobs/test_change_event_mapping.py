from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import JsonValue

from app.jobs.change_detection import JobVersionComparable
from app.jobs.changes import FieldChange, FieldChangeType
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
    _build_comparable_version,
    _build_job_change_events,
    _build_job_version,
)


@pytest.mark.parametrize(
    ("change_type", "old_value", "new_value"),
    [
        (FieldChangeType.MODIFIED, "remote", "hybrid"),
        (FieldChangeType.ADDED, None, "65000"),
        (FieldChangeType.REMOVED, "EUR", None),
        (
            FieldChangeType.MODIFIED,
            {"departments": ["Engineering"], "active": True, "count": 1},
            {"departments": ["Platform"], "nested": {"values": [None, 1.5]}},
        ),
    ],
)
def test_mapping_preserves_provenance_type_and_json_values(
    change_type: FieldChangeType,
    old_value: JsonValue,
    new_value: JsonValue,
) -> None:
    job_id, previous_id, next_id = uuid4(), uuid4(), uuid4()
    detected_at = datetime(2026, 10, 8, 12, tzinfo=UTC)
    change = FieldChange("example_field", change_type, old_value, new_value)

    events = _build_job_change_events(
        job_id=job_id,
        from_version_id=previous_id,
        to_version_id=next_id,
        detected_at=detected_at,
        changes=[change],
    )

    assert len(events) == 1
    event = events[0]
    assert event.job_id == job_id
    assert event.from_version_id == previous_id
    assert event.to_version_id == next_id
    assert event.field_name == "example_field"
    assert event.change_type == change_type.value
    assert event.old_value == old_value
    assert event.new_value == new_value
    assert event.detected_at == detected_at


def test_orm_adapter_copies_all_material_fields_and_nested_metadata() -> None:
    canonical = CanonicalJobInput.model_validate(
        {
            "external_job_id": "1001",
            "title": "Engineer",
            "description": "<p>Build APIs.</p>",
            "location_text": "Berlin, Germany",
            "city": "Berlin",
            "region": "Berlin",
            "country_code": "DE",
            "workplace_type": "hybrid",
            "employment_type": "full_time",
            "salary_min": Decimal("65000.00"),
            "salary_max": Decimal("80000.00"),
            "salary_currency": "EUR",
            "salary_period": "year",
            "source_url": "https://example.com/jobs/1001",
            "canonical_metadata": {"nested": {"values": ["original"]}},
        }
    )
    version = _build_job_version(
        job_id=uuid4(),
        source_observation_id=uuid4(),
        version_number=7,
        canonical_job=canonical,
        content_hash="a" * 64,
        effective_from=datetime(2026, 10, 8, 12, tzinfo=UTC),
    )

    comparable = _build_comparable_version(version)

    assert comparable == JobVersionComparable.from_canonical_job(canonical)
    nested = version.canonical_metadata["nested"]
    assert isinstance(nested, dict)
    nested["values"].append("later mutation")
    canonical.canonical_metadata.clear()
    assert comparable.canonical_metadata == {"nested": {"values": ["original"]}}
