from decimal import Decimal
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
CountryCode = Annotated[str, Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")]
CurrencyCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")]


class CanonicalJobInput(BaseModel):
    """Provider-independent job content before persistence and versioning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    external_job_id: NonBlankString
    title: NonBlankString
    description: str | None = None

    location_text: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: CountryCode | None = None

    workplace_type: str | None = None
    employment_type: str | None = None

    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: CurrencyCode | None = None
    salary_period: str | None = None

    source_url: HttpUrl
    source_published_at: AwareDatetime | None = None
    source_updated_at: AwareDatetime | None = None

    canonical_metadata: dict[str, JsonValue] = Field(default_factory=dict)
