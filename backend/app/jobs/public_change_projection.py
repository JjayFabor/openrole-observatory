from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from app.jobs.changes import FieldChangeType
from app.jobs.public_change_schemas import (
    PublicDescriptionChange,
    PublicJobChange,
    PublicJobChangeGroup,
    PublicSalaryChange,
    PublicSalaryValue,
    PublicTextChange,
    PublicTextChangeField,
)

PUBLIC_TEXT_CHANGE_FIELDS = (
    "title",
    "location_text",
    "city",
    "region",
    "country_code",
    "workplace_type",
    "employment_type",
)
SALARY_CHANGE_FIELDS = (
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
)
PUBLIC_STORED_CHANGE_FIELDS = (
    *PUBLIC_TEXT_CHANGE_FIELDS,
    *SALARY_CHANGE_FIELDS,
    "description",
)
PUBLIC_CHANGE_ORDER = (*PUBLIC_TEXT_CHANGE_FIELDS, "salary", "description")


@dataclass(frozen=True, slots=True)
class StoredPublicChange:
    """Internal grouping keys and narrowly selected context, never an API model."""

    from_version_id: UUID
    to_version_id: UUID
    detected_at: datetime
    field_name: str
    change_type: str
    old_value: JsonValue
    new_value: JsonValue
    old_salary: PublicSalaryValue | None = None
    new_salary: PublicSalaryValue | None = None


def _text(value: JsonValue) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("Public text changes require text or null.")


def _change(record: StoredPublicChange) -> PublicJobChange:
    recorded_type = FieldChangeType(record.change_type)
    if record.field_name == "description":
        return PublicDescriptionChange(change_type=recorded_type)
    if record.field_name in SALARY_CHANGE_FIELDS:
        if record.old_salary is None and record.new_salary is None:
            raise ValueError("A salary change requires structured salary information.")
        # Presence describes salary information, including units without amounts.
        # Persisted events establish the change; snapshots supply unchanged context.
        kind = (
            FieldChangeType.ADDED
            if record.old_salary is None
            else FieldChangeType.REMOVED
            if record.new_salary is None
            else FieldChangeType.MODIFIED
        )
        return PublicSalaryChange(
            change_type=kind,
            old_value=record.old_salary,
            new_value=record.new_salary,
        )
    if record.field_name not in PUBLIC_TEXT_CHANGE_FIELDS:
        raise ValueError("Uncurated change field reached the public projection.")
    return PublicTextChange(
        field=cast(PublicTextChangeField, record.field_name),
        change_type=recorded_type,
        old_value=_text(record.old_value),
        new_value=_text(record.new_value),
    )


def project_public_change_groups(
    records: list[StoredPublicChange],
) -> list[PublicJobChangeGroup]:
    transitions: dict[tuple[UUID, UUID], list[StoredPublicChange]] = {}
    for record in records:
        transitions.setdefault(
            (record.from_version_id, record.to_version_id),
            [],
        ).append(record)

    ordered = sorted(
        transitions.values(),
        key=lambda items: (
            items[0].detected_at,
            items[0].to_version_id.int,
            items[0].from_version_id.int,
        ),
        reverse=True,
    )
    groups: list[PublicJobChangeGroup] = []
    for transition in ordered:
        observed_at = transition[0].detected_at
        if any(item.detected_at != observed_at for item in transition):
            raise ValueError(
                "A persisted transition has inconsistent observation times."
            )
        changes: dict[str, PublicJobChange] = {}
        for record in transition:
            change = _change(record)
            changes.setdefault(change.field, change)
        groups.append(
            PublicJobChangeGroup(
                observed_at=observed_at,
                changes=[
                    changes[field] for field in PUBLIC_CHANGE_ORDER if field in changes
                ],
            )
        )
    return groups
