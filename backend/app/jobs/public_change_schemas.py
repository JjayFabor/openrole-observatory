from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from app.jobs.changes import FieldChangeType

PublicTextChangeField = Literal[
    "title",
    "location_text",
    "city",
    "region",
    "country_code",
    "workplace_type",
    "employment_type",
]


class PublicSalaryValue(BaseModel):
    min: Decimal | None
    max: Decimal | None
    currency: str | None
    period: str | None


class PublicTextChange(BaseModel):
    field: PublicTextChangeField
    change_type: FieldChangeType
    old_value: str | None
    new_value: str | None


class PublicSalaryChange(BaseModel):
    field: Literal["salary"] = "salary"
    change_type: FieldChangeType
    old_value: PublicSalaryValue | None
    new_value: PublicSalaryValue | None


class PublicDescriptionChange(BaseModel):
    field: Literal["description"] = "description"
    change_type: FieldChangeType


PublicJobChange = Annotated[
    PublicTextChange | PublicSalaryChange | PublicDescriptionChange,
    Field(discriminator="field"),
]


class PublicJobChangeGroup(BaseModel):
    observed_at: AwareDatetime
    changes: list[PublicJobChange]


class PublicJobChangesResponse(BaseModel):
    job_id: UUID
    items: list[PublicJobChangeGroup]
    limit: int
