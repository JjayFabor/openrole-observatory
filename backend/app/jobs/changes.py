from dataclasses import dataclass
from enum import StrEnum

from pydantic import JsonValue


class FieldChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One canonical field difference, represented independently of persistence."""

    field_name: str
    change_type: FieldChangeType
    old_value: JsonValue
    new_value: JsonValue
