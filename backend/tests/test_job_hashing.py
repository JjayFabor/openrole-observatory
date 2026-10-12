import re
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

import pytest

from app.jobs.hashing import (
    build_canonical_job_hash_payload,
    compute_canonical_job_hash,
    serialize_canonical_job_hash_payload,
)
from app.jobs.schemas import CanonicalJobInput
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.validation import parse_greenhouse_response

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "greenhouse"


class ExampleWorkplaceType(StrEnum):
    REMOTE = "remote"


def canonical_job(**overrides: object) -> CanonicalJobInput:
    values: dict[str, object] = {
        "external_job_id": "1001",
        "title": "Backend Engineer",
        "description": "<p>Build reliable APIs.</p>",
        "location_text": "Berlin, Germany",
        "source_url": "https://boards.greenhouse.io/example/jobs/1001",
    }
    values.update(overrides)
    return CanonicalJobInput.model_validate(values)


def test_hash_payload_uses_only_explicit_material_fields() -> None:
    payload = build_canonical_job_hash_payload(canonical_job())

    assert set(payload) == {
        "title",
        "description",
        "location_text",
        "city",
        "region",
        "country_code",
        "workplace_type",
        "employment_type",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "source_url",
        "canonical_metadata",
    }
    assert "external_job_id" not in payload
    assert "source_published_at" not in payload
    assert "source_updated_at" not in payload


def test_hash_is_deterministic_across_greenhouse_mapping() -> None:
    fixture = (FIXTURE_ROOT / "jobs_v1.json").read_text(encoding="utf-8")
    source_job = parse_greenhouse_response(fixture).valid_records[0]

    first = compute_canonical_job_hash(map_greenhouse_job(source_job))
    second = compute_canonical_job_hash(map_greenhouse_job(source_job))

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)


@pytest.mark.parametrize(
    "change",
    [
        {"title": "Senior Backend Engineer"},
        {"description": "<p>Build reliable APIs and data pipelines.</p>"},
        {"location_text": "Remote — Europe"},
        {"source_url": "https://boards.greenhouse.io/example/jobs/1001-new"},
        {"canonical_metadata": {"departments": [{"id": 2, "name": "Data"}]}},
    ],
)
def test_meaningful_content_changes_produce_different_hashes(
    change: dict[str, object],
) -> None:
    baseline = canonical_job()
    changed = canonical_job(**change)

    assert compute_canonical_job_hash(baseline) != compute_canonical_job_hash(changed)


def test_null_values_have_one_stable_representation() -> None:
    first = canonical_job(description=None, location_text=None)
    second = canonical_job(description=None, location_text=None)

    serialized = serialize_canonical_job_hash_payload(first)

    assert compute_canonical_job_hash(first) == compute_canonical_job_hash(second)
    assert b'"description":null' in serialized
    assert b'"location_text":null' in serialized


def test_metadata_dictionary_insertion_order_does_not_affect_hash() -> None:
    first = canonical_job(
        canonical_metadata={
            "departments": [{"id": 1, "name": "Engineering"}],
            "offices": [{"id": 2, "name": "Berlin"}],
        }
    )
    second = canonical_job(
        canonical_metadata={
            "offices": [{"name": "Berlin", "id": 2}],
            "departments": [{"name": "Engineering", "id": 1}],
        }
    )

    assert compute_canonical_job_hash(first) == compute_canonical_job_hash(second)


def test_external_id_and_source_timestamps_do_not_affect_hash() -> None:
    first = canonical_job(
        external_job_id="1001",
        source_published_at=datetime(2026, 10, 1, 9, tzinfo=UTC),
        source_updated_at=datetime(2026, 10, 2, 9, tzinfo=UTC),
    )
    second = canonical_job(
        external_job_id="different-logical-job",
        source_published_at=datetime(
            2026,
            11,
            1,
            17,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        source_updated_at=datetime(2026, 11, 2, 9, tzinfo=UTC),
    )

    assert compute_canonical_job_hash(first) == compute_canonical_job_hash(second)


def test_equivalent_decimals_serialize_without_float_conversion() -> None:
    whole = canonical_job(
        salary_min=Decimal("65000"),
        salary_max=Decimal("80000.0"),
        salary_currency="EUR",
        salary_period="year",
    )
    scaled = canonical_job(
        salary_min=Decimal("65000.00"),
        salary_max=Decimal("80000.000"),
        salary_currency="EUR",
        salary_period="year",
    )
    changed = canonical_job(
        salary_min=Decimal("65001.00"),
        salary_max=Decimal("80000.00"),
        salary_currency="EUR",
        salary_period="year",
    )

    serialized = serialize_canonical_job_hash_payload(scaled)

    assert compute_canonical_job_hash(whole) == compute_canonical_job_hash(scaled)
    assert compute_canonical_job_hash(scaled) != compute_canonical_job_hash(changed)
    assert b'"salary_min":"65000"' in serialized
    assert b'"salary_max":"80000"' in serialized


def test_enum_values_serialize_independently_of_python_enum_names() -> None:
    enum_value = canonical_job(workplace_type=ExampleWorkplaceType.REMOTE)
    plain_string = canonical_job(workplace_type="remote")

    serialized = serialize_canonical_job_hash_payload(enum_value)

    assert compute_canonical_job_hash(enum_value) == compute_canonical_job_hash(
        plain_string
    )
    assert b'"workplace_type":"remote"' in serialized
    assert b"ExampleWorkplaceType" not in serialized


def test_department_and_office_order_does_not_affect_hash() -> None:
    department_a = {"id": 1, "name": "Engineering"}
    department_b = {"id": 2, "name": "Data"}
    office_a = {"id": 10, "name": "Berlin"}
    office_b = {"id": 11, "name": "London"}
    first = canonical_job(
        canonical_metadata={
            "departments": [department_a, department_b],
            "offices": [office_a, office_b],
        }
    )
    second = canonical_job(
        canonical_metadata={
            "departments": [department_b, department_a],
            "offices": [office_b, office_a],
        }
    )

    assert compute_canonical_job_hash(first) == compute_canonical_job_hash(second)


def test_other_list_order_remains_meaningful() -> None:
    first = canonical_job(canonical_metadata={"steps": ["screen", "interview"]})
    second = canonical_job(canonical_metadata={"steps": ["interview", "screen"]})

    assert compute_canonical_job_hash(first) != compute_canonical_job_hash(second)


def test_serialization_does_not_reorder_input_metadata() -> None:
    job = canonical_job(
        canonical_metadata={
            "departments": [
                {"id": 2, "name": "Data"},
                {"id": 1, "name": "Engineering"},
            ]
        }
    )
    metadata_before = job.model_dump(mode="json")["canonical_metadata"]

    serialize_canonical_job_hash_payload(job)

    assert job.model_dump(mode="json")["canonical_metadata"] == metadata_before


def test_serialization_is_compact_sorted_utf8_json() -> None:
    job = canonical_job(title="Développeur — API")

    serialized = serialize_canonical_job_hash_payload(job)

    assert serialized.startswith(b'{"canonical_metadata":')
    assert "Développeur — API".encode() in serialized
    assert b'": ' not in serialized
