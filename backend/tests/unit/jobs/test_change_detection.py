import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, fields, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue

from app.jobs.change_detection import (
    TRACKED_JOB_FIELDS,
    JobVersionComparable,
    diff_job_versions,
)
from app.jobs.changes import FieldChange, FieldChangeType
from app.jobs.hashing import (
    build_canonical_job_hash_payload,
    compute_canonical_job_hash,
)
from app.jobs.schemas import CanonicalJobInput
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.validation import parse_greenhouse_response

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BASELINE = JobVersionComparable(
    title="Backend Engineer",
    source_url="https://example.com/jobs/1001",
)
FIELD_UPDATES: tuple[tuple[str, object], ...] = (
    ("title", "Senior Backend Engineer"),
    ("description", "<p>Build APIs.</p>"),
    ("location_text", "Berlin, Germany"),
    ("city", "Berlin"),
    ("region", "Berlin"),
    ("country_code", "DE"),
    ("workplace_type", "hybrid"),
    ("employment_type", "full_time"),
    ("salary_min", Decimal("65000.00")),
    ("salary_max", Decimal("80000.00")),
    ("salary_currency", "EUR"),
    ("salary_period", "year"),
    ("source_url", "https://example.com/jobs/1001-new"),
    ("canonical_metadata", {"department": "Engineering"}),
)


class WorkplaceType(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"


def canonical_job(**overrides: object) -> CanonicalJobInput:
    return CanonicalJobInput.model_validate(
        {
            "external_job_id": "1001",
            "title": BASELINE.title,
            "source_url": BASELINE.source_url,
            **overrides,
        }
    )


def test_identical_snapshots_and_null_fields_produce_no_changes() -> None:
    assert diff_job_versions(BASELINE, BASELINE) == []
    assert diff_job_versions(BASELINE, replace(BASELINE)) == []


def test_title_modification() -> None:
    assert diff_job_versions(
        BASELINE, replace(BASELINE, title="Senior Backend Engineer")
    ) == [
        FieldChange(
            "title",
            FieldChangeType.MODIFIED,
            "Backend Engineer",
            "Senior Backend Engineer",
        )
    ]


@pytest.mark.parametrize(
    ("old_salary", "new_salary", "change_type", "old_value", "new_value"),
    [
        (None, Decimal("65000.00"), FieldChangeType.ADDED, None, "65000"),
        (Decimal("65000.00"), None, FieldChangeType.REMOVED, "65000", None),
        (
            Decimal("65000.00"),
            Decimal("80000.00"),
            FieldChangeType.MODIFIED,
            "65000",
            "80000",
        ),
        (None, Decimal("0.10"), FieldChangeType.ADDED, None, "0.1"),
        (None, Decimal("0.00"), FieldChangeType.ADDED, None, "0"),
    ],
)
def test_salary_classification_and_exact_json_strings(
    old_salary: Decimal | None,
    new_salary: Decimal | None,
    change_type: FieldChangeType,
    old_value: JsonValue,
    new_value: JsonValue,
) -> None:
    changes = diff_job_versions(
        replace(BASELINE, salary_min=old_salary),
        replace(BASELINE, salary_min=new_salary),
    )
    assert changes == [FieldChange("salary_min", change_type, old_value, new_value)]
    assert json.loads(json.dumps(asdict(changes[0])))["new_value"] == new_value


def test_equivalent_decimals_are_unchanged() -> None:
    previous = canonical_job(salary_min=Decimal("65000.00"), salary_max=Decimal("0.0"))
    current = canonical_job(salary_min=Decimal("65000"), salary_max=Decimal("-0.00"))

    assert compute_canonical_job_hash(previous) == compute_canonical_job_hash(current)
    assert (
        diff_job_versions(
            JobVersionComparable.from_canonical_job(previous),
            JobVersionComparable.from_canonical_job(current),
        )
        == []
    )


def test_enum_values_serialize_as_plain_strings() -> None:
    previous = replace(BASELINE, workplace_type=WorkplaceType.REMOTE)
    current = replace(BASELINE, workplace_type=WorkplaceType.HYBRID)

    assert diff_job_versions(previous, replace(previous, workplace_type="remote")) == []
    changes = diff_job_versions(previous, current)
    assert changes == [
        FieldChange("workplace_type", FieldChangeType.MODIFIED, "remote", "hybrid")
    ]
    assert type(changes[0].old_value) is str
    assert type(changes[0].new_value) is str


def test_multiple_changes_follow_fixed_field_order() -> None:
    current = replace(
        BASELINE,
        location_text="Berlin",
        workplace_type="hybrid",
        salary_min=Decimal("65000"),
        salary_max=Decimal("80000"),
    )
    changes = diff_job_versions(BASELINE, current)

    assert [change.field_name for change in changes] == [
        "location_text",
        "workplace_type",
        "salary_min",
        "salary_max",
    ]
    assert len(changes) == 4
    assert diff_job_versions(BASELINE, current) == changes


def test_snapshot_contract_excludes_operational_fields() -> None:
    excluded = {
        "id",
        "job_id",
        "external_job_id",
        "source_observation_id",
        "version_number",
        "content_hash",
        "effective_from",
        "effective_to",
        "is_current",
        "source_published_at",
        "source_updated_at",
        "created_at",
    }
    snapshot_fields = {item.name for item in fields(JobVersionComparable)}

    assert snapshot_fields.isdisjoint(excluded)
    assert snapshot_fields == set(TRACKED_JOB_FIELDS)
    assert set(TRACKED_JOB_FIELDS) == set(
        build_canonical_job_hash_payload(canonical_job())
    )


def test_canonical_identity_and_source_timestamps_are_ignored() -> None:
    previous = canonical_job()
    current = canonical_job(
        external_job_id="another-id",
        source_published_at=datetime(2026, 10, 1, tzinfo=UTC),
        source_updated_at=datetime(2026, 10, 8, tzinfo=UTC),
    )

    assert compute_canonical_job_hash(previous) == compute_canonical_job_hash(current)
    assert (
        diff_job_versions(
            JobVersionComparable.from_canonical_job(previous),
            JobVersionComparable.from_canonical_job(current),
        )
        == []
    )


def test_dictionary_key_order_is_not_a_change() -> None:
    previous = canonical_job(canonical_metadata={"a": 1, "nested": {"x": 2, "y": None}})
    current = canonical_job(canonical_metadata={"nested": {"y": None, "x": 2}, "a": 1})

    assert compute_canonical_job_hash(previous) == compute_canonical_job_hash(current)
    assert (
        diff_job_versions(
            JobVersionComparable.from_canonical_job(previous),
            JobVersionComparable.from_canonical_job(current),
        )
        == []
    )


def test_metadata_value_change_is_structural() -> None:
    previous = replace(BASELINE, canonical_metadata={"department": "Engineering"})
    current = replace(BASELINE, canonical_metadata={"department": "Platform"})

    assert diff_job_versions(previous, current) == [
        FieldChange(
            "canonical_metadata",
            FieldChangeType.MODIFIED,
            {"department": "Engineering"},
            {"department": "Platform"},
        )
    ]


@pytest.mark.parametrize("collection", ["departments", "offices"])
def test_outer_department_and_office_order_is_ignored(collection: str) -> None:
    first = {"id": 1, "name": "Engineering"}
    second = {"id": 2, "name": "Platform"}
    previous = canonical_job(canonical_metadata={collection: [first, second]})
    current = canonical_job(canonical_metadata={collection: [second, first]})

    assert compute_canonical_job_hash(previous) == compute_canonical_job_hash(current)
    assert (
        diff_job_versions(
            JobVersionComparable.from_canonical_job(previous),
            JobVersionComparable.from_canonical_job(current),
        )
        == []
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {"steps": ["interview", "screen"]},
        {"nested": {"departments": ["interview", "screen"]}},
    ],
)
def test_other_and_nested_list_order_remains_meaningful(
    metadata: dict[str, JsonValue],
) -> None:
    previous_metadata: dict[str, JsonValue] = (
        {"steps": ["screen", "interview"]}
        if "steps" in metadata
        else {"nested": {"departments": ["screen", "interview"]}}
    )
    previous = canonical_job(canonical_metadata=previous_metadata)
    current = canonical_job(canonical_metadata=metadata)

    assert compute_canonical_job_hash(previous) != compute_canonical_job_hash(current)
    changes = diff_job_versions(
        JobVersionComparable.from_canonical_job(previous),
        JobVersionComparable.from_canonical_job(current),
    )
    assert changes == [
        FieldChange(
            "canonical_metadata", FieldChangeType.MODIFIED, previous_metadata, metadata
        )
    ]


@pytest.mark.parametrize(
    ("old_value", "new_value"),
    [
        (True, 1),
        (1, 1.0),
        (False, 0),
        (-0.0, 0.0),
    ],
)
def test_json_value_distinctions_agree_with_hash(
    old_value: JsonValue,
    new_value: JsonValue,
) -> None:
    previous = canonical_job(canonical_metadata={"values": [{"flag": old_value}]})
    current = canonical_job(canonical_metadata={"values": [{"flag": new_value}]})

    assert compute_canonical_job_hash(previous) != compute_canonical_job_hash(current)
    changes = diff_job_versions(
        JobVersionComparable.from_canonical_job(previous),
        JobVersionComparable.from_canonical_job(current),
    )
    assert len(changes) == 1
    assert changes[0].field_name == "canonical_metadata"
    assert changes[0].change_type is FieldChangeType.MODIFIED


def test_description_changes_include_complete_canonical_text() -> None:
    previous = replace(BASELINE, description="<p>Build APIs.</p>")
    current = replace(BASELINE, description="<p>Build APIs and data pipelines.</p>")

    assert diff_job_versions(previous, current) == [
        FieldChange(
            "description",
            FieldChangeType.MODIFIED,
            previous.description,
            current.description,
        )
    ]


@pytest.mark.parametrize(
    ("old_value", "new_value", "change_type"),
    [
        ("", None, FieldChangeType.REMOVED),
        (None, "", FieldChangeType.ADDED),
        ("", " ", FieldChangeType.MODIFIED),
    ],
)
def test_empty_string_is_distinct_from_null_and_whitespace(
    old_value: str | None,
    new_value: str | None,
    change_type: FieldChangeType,
) -> None:
    assert diff_job_versions(
        replace(BASELINE, description=old_value),
        replace(BASELINE, description=new_value),
    ) == [FieldChange("description", change_type, old_value, new_value)]


@pytest.mark.parametrize(("field_name", "value"), FIELD_UPDATES)
def test_every_tracked_field_explains_a_material_hash_change(
    field_name: str,
    value: object,
) -> None:
    previous = canonical_job()
    current = canonical_job(**{field_name: value})

    assert compute_canonical_job_hash(previous) != compute_canonical_job_hash(current)
    changes = diff_job_versions(
        JobVersionComparable.from_canonical_job(previous),
        JobVersionComparable.from_canonical_job(current),
    )
    assert len(changes) == 1
    assert changes[0].field_name == field_name


def test_all_changes_are_ordered_and_json_serializable() -> None:
    previous = JobVersionComparable.from_canonical_job(canonical_job())
    current = JobVersionComparable.from_canonical_job(
        canonical_job(**dict(FIELD_UPDATES))
    )
    changes = diff_job_versions(previous, current)

    assert tuple(change.field_name for change in changes) == TRACKED_JOB_FIELDS
    serialized = json.loads(
        json.dumps([asdict(change) for change in changes], allow_nan=False)
    )
    assert serialized[0]["change_type"] == "modified"
    assert serialized[8]["new_value"] == "65000"
    assert diff_job_versions(previous, current) == changes


@pytest.mark.parametrize(
    ("external_id", "expected_fields"),
    [
        ("1001", ["location_text", "canonical_metadata"]),
        ("1002", ["title"]),
        ("1003", []),
        ("1004", []),
    ],
)
def test_greenhouse_fixtures_cross_canonical_boundary_without_persistence(
    external_id: str,
    expected_fields: list[str],
) -> None:
    def mapped_fixture(name: str) -> CanonicalJobInput:
        validation = parse_greenhouse_response(
            (PROJECT_ROOT / "fixtures" / "greenhouse" / name).read_bytes()
        )
        job = next(
            record
            for record in validation.valid_records
            if str(record.id) == external_id
        )
        return map_greenhouse_job(job)

    previous = mapped_fixture("jobs_v1.json")
    current = mapped_fixture("jobs_v2.json")
    changes = diff_job_versions(
        JobVersionComparable.from_canonical_job(previous),
        JobVersionComparable.from_canonical_job(current),
    )

    assert [change.field_name for change in changes] == expected_fields
    assert all(change.change_type is FieldChangeType.MODIFIED for change in changes)
    assert (
        compute_canonical_job_hash(previous) != compute_canonical_job_hash(current)
    ) == bool(changes)


def test_normalization_and_result_metadata_do_not_mutate_inputs() -> None:
    previous = replace(
        BASELINE,
        canonical_metadata={
            "departments": [
                {"id": 2, "name": "Platform"},
                {"id": 1, "name": "Engineering"},
            ]
        },
    )
    current = replace(
        BASELINE, canonical_metadata={"departments": [{"id": 3, "name": "Data"}]}
    )
    before = deepcopy((previous.canonical_metadata, current.canonical_metadata))
    changes = diff_job_versions(previous, current)

    assert (previous.canonical_metadata, current.canonical_metadata) == before
    assert isinstance(changes[0].old_value, dict)
    assert isinstance(changes[0].new_value, dict)
    changes[0].old_value["extra"] = True
    changes[0].new_value["extra"] = True
    assert (previous.canonical_metadata, current.canonical_metadata) == before


def test_canonical_adapter_copies_metadata() -> None:
    canonical = canonical_job(canonical_metadata={"nested": {"value": 1}})
    snapshot = JobVersionComparable.from_canonical_job(canonical)
    nested = snapshot.canonical_metadata["nested"]
    assert isinstance(nested, dict)
    nested["value"] = 2

    assert canonical.canonical_metadata == {"nested": {"value": 1}}


@pytest.mark.parametrize(
    ("target", "attribute"),
    [
        (
            FieldChange(
                "title", FieldChangeType.MODIFIED, "Engineer", "Senior Engineer"
            ),
            "new_value",
        ),
        (BASELINE, "title"),
    ],
)
def test_snapshot_and_result_attributes_are_frozen(
    target: FieldChange | JobVersionComparable,
    attribute: str,
) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(target, attribute, "Another title")


@pytest.mark.parametrize(
    "value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
)
def test_non_finite_decimal_is_rejected(value: Decimal) -> None:
    with pytest.raises(ValueError, match="Decimal values must be finite"):
        diff_job_versions(BASELINE, replace(BASELINE, salary_min=value))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_metadata_float_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="float values must be finite"):
        diff_job_versions(
            BASELINE, replace(BASELINE, canonical_metadata={"value": value})
        )


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"value": object()}, "Unsupported canonical hash value: object"),
        ({1: "value"}, "dictionary keys must be strings"),
    ],
)
def test_unsupported_metadata_is_not_silently_stringified(
    metadata: dict[object, object],
    message: str,
) -> None:
    invalid = replace(BASELINE, canonical_metadata=cast(dict[str, JsonValue], metadata))
    with pytest.raises(TypeError, match=message):
        diff_job_versions(BASELINE, invalid)


def test_non_snapshot_input_is_rejected_before_attribute_access() -> None:
    class LazyObject:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"unexpected attribute access: {name}")

    with pytest.raises(TypeError, match="requires JobVersionComparable snapshots"):
        diff_job_versions(cast(JobVersionComparable, LazyObject()), BASELINE)


def test_diff_import_and_execution_need_no_database_or_api_modules() -> None:
    script = """
import importlib.abc
import sys

class BlockInfrastructure(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = ('sqlalchemy', 'asyncpg', 'fastapi', 'httpx', 'boto3',
                   'app.database', 'app.config', 'app.storage')
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise ImportError('Infrastructure import blocked: ' + fullname)

sys.meta_path.insert(0, BlockInfrastructure())
from app.jobs.change_detection import JobVersionComparable, diff_job_versions
from app.jobs.changes import FieldChangeType
before = JobVersionComparable(title='Engineer', source_url='https://example.com')
after = JobVersionComparable(title='Senior Engineer', source_url='https://example.com')
changes = diff_job_versions(before, after)
assert len(changes) == 1
assert changes[0].change_type is FieldChangeType.MODIFIED
assert not any(name.startswith(('sqlalchemy', 'fastapi', 'asyncpg')) for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT / "backend",
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": "unavailable"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
