from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import JsonValue

from app.jobs.public_change_projection import (
    SALARY_CHANGE_FIELDS,
    StoredPublicChange,
    project_public_change_groups,
)
from app.jobs.public_change_schemas import PublicSalaryValue

AT = datetime(2026, 10, 8, 12, tzinfo=UTC)
FROM_ID = UUID(int=1)
TO_ID = UUID(int=2)


def record(
    field: str,
    kind: str = "modified",
    *,
    from_version_id: UUID = FROM_ID,
    to_version_id: UUID = TO_ID,
    detected_at: datetime = AT,
    old_value: JsonValue = "Before",
    new_value: JsonValue = "After",
    old_salary: PublicSalaryValue | None = None,
    new_salary: PublicSalaryValue | None = None,
) -> StoredPublicChange:
    return StoredPublicChange(
        from_version_id,
        to_version_id,
        detected_at,
        field,
        kind,
        old_value,
        new_value,
        old_salary,
        new_salary,
    )


@pytest.mark.parametrize(
    "kind,old,new",
    [
        ("added", None, "Berlin"),
        ("removed", "Berlin", None),
        ("modified", "Remote", "Berlin"),
    ],
)
def test_text_projection_retains_facts_and_nulls(
    kind: str, old: str | None, new: str | None
) -> None:
    groups = project_public_change_groups(
        [record("location_text", kind, old_value=old, new_value=new)]
    )
    assert groups[0].model_dump(mode="json") == {
        "observed_at": "2026-10-08T12:00:00Z",
        "changes": [
            {
                "field": "location_text",
                "change_type": kind,
                "old_value": old,
                "new_value": new,
            }
        ],
    }


@pytest.mark.parametrize("kind", ["added", "removed", "modified"])
def test_description_is_only_a_marker_even_if_internal_values_contain_bodies(
    kind: str,
) -> None:
    group = project_public_change_groups(
        [
            record(
                "description",
                kind,
                old_value="<script>private-before</script>",
                new_value={"provider": "private-after"},
            )
        ]
    )[0]
    assert group.model_dump(mode="json")["changes"] == [
        {"field": "description", "change_type": kind}
    ]
    assert "private" not in group.model_dump_json()


def test_related_salary_events_become_one_complete_exact_salary_change() -> None:
    salary = PublicSalaryValue(
        min=Decimal("0.00"), max=Decimal("90000.99"), currency="USD", period="year"
    )
    records = [
        record(field, "added", old_salary=None, new_salary=salary)
        for field in SALARY_CHANGE_FIELDS
    ]
    group = project_public_change_groups(records)[0]
    assert len(group.changes) == 1
    assert group.model_dump(mode="json")["changes"] == [
        {
            "field": "salary",
            "change_type": "added",
            "old_value": None,
            "new_value": {
                "min": "0.00",
                "max": "90000.99",
                "currency": "USD",
                "period": "year",
            },
        }
    ]


def test_salary_semantics_include_partial_and_unit_only_information() -> None:
    units = PublicSalaryValue(min=None, max=None, currency="USD", period=None)
    partial = PublicSalaryValue(
        min=Decimal("10.01"), max=None, currency=None, period=None
    )
    for before, after, kind in [
        (None, units, "added"),
        (units, partial, "modified"),
        (partial, None, "removed"),
    ]:
        change = project_public_change_groups(
            [record("salary_min", old_salary=before, new_salary=after)]
        )[0].changes[0]
        assert change.change_type == kind
        assert change.model_dump()["old_value"] == (
            before.model_dump() if before else None
        )
        assert change.model_dump()["new_value"] == (
            after.model_dump() if after else None
        )


def test_groups_are_newest_first_and_same_time_transitions_stay_separate() -> None:
    groups = project_public_change_groups(
        [
            record("description"),
            record("title"),
            record(
                "workplace_type", from_version_id=UUID(int=2), to_version_id=UUID(int=3)
            ),
            record(
                "employment_type",
                from_version_id=UUID(int=3),
                to_version_id=UUID(int=4),
                detected_at=AT + timedelta(days=1),
            ),
        ]
    )
    assert [[change.field for change in group.changes] for group in groups] == [
        ["employment_type"],
        ["workplace_type"],
        ["title", "description"],
    ]
    assert all(
        set(group.model_dump()) == {"observed_at", "changes"} for group in groups
    )


@pytest.mark.parametrize(
    "field", ["canonical_metadata", "source_url", "pipeline_run_id"]
)
def test_uncurated_fields_cannot_be_projected(field: str) -> None:
    with pytest.raises(ValueError):
        project_public_change_groups([record(field)])


def test_structured_text_values_and_inconsistent_timestamps_fail_visibly() -> None:
    with pytest.raises(ValueError):
        project_public_change_groups([record("title", new_value={"private": "debug"})])
    with pytest.raises(ValueError):
        project_public_change_groups(
            [
                record("title"),
                record("description", detected_at=AT + timedelta(seconds=1)),
            ]
        )
    with pytest.raises(ValueError):
        project_public_change_groups([record("salary_min")])
