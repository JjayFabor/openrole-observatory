from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
)


def _require_non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankString = Annotated[str, AfterValidator(_require_non_blank)]
PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeStrictInt = Annotated[int, Field(strict=True, ge=0)]


class GreenhouseLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: NonBlankString


class GreenhouseDepartment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: PositiveStrictInt
    name: NonBlankString
    parent_id: PositiveStrictInt | None = None
    child_ids: list[PositiveStrictInt] | None = None


class GreenhouseOffice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: PositiveStrictInt
    name: NonBlankString
    location: str | None = None
    parent_id: PositiveStrictInt | None = None
    child_ids: list[PositiveStrictInt] | None = None


class GreenhouseMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: PositiveStrictInt
    name: NonBlankString
    value_type: NonBlankString
    value: JsonValue


class GreenhouseJob(BaseModel):
    """Provider-native fields used from one Greenhouse job-board record."""

    model_config = ConfigDict(extra="ignore")

    id: PositiveStrictInt
    internal_job_id: PositiveStrictInt | None = None
    title: NonBlankString
    updated_at: AwareDatetime | None = None
    requisition_id: str | None = None
    location: GreenhouseLocation | None = None
    absolute_url: HttpUrl
    language: str | None = None
    metadata: list[GreenhouseMetadata] | None = None
    content: str | None = None
    departments: list[GreenhouseDepartment] | None = None
    offices: list[GreenhouseOffice] | None = None


class GreenhouseResponseMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: NonNegativeStrictInt


class GreenhouseJobBoardResponse(BaseModel):
    """Top-level envelope that deliberately leaves child records unvalidated."""

    model_config = ConfigDict(extra="ignore")

    jobs: list[object]
    meta: GreenhouseResponseMeta | None = None
