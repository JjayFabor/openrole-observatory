from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, HttpUrl, TypeAdapter

from app.jobs.models import JobLifecycleStatus
from app.sources.models import SourceProvider


class PublicWorkplaceFilter(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class PublicEmploymentFilter(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    VOLUNTEER = "volunteer"
    OTHER = "other"


_http_url = TypeAdapter(HttpUrl)


def validate_public_url(value: str) -> str:
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("Public links must be absolute HTTP(S) URLs.")
    url = _http_url.validate_python(value)
    if url.username is not None or url.password is not None:
        raise ValueError("Public links must not contain credentials.")
    return value


PublicHttpUrl = Annotated[str, AfterValidator(validate_public_url)]


class PublicCompanySummary(BaseModel):
    name: str
    domain: str | None


class PublicCompanyDetail(PublicCompanySummary):
    careers_url: PublicHttpUrl | None


class PublicJobSourceSummary(BaseModel):
    provider: SourceProvider


class PublicJobListItem(BaseModel):
    id: UUID
    title: str
    company: PublicCompanySummary
    location_text: str | None
    city: str | None
    region: str | None
    country_code: str | None
    workplace_type: str | None
    employment_type: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    salary_period: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    source: PublicJobSourceSummary


class PublicJobListResponse(BaseModel):
    items: list[PublicJobListItem]
    total: int
    limit: int
    offset: int


class PublicJobSitemapItem(BaseModel):
    id: UUID


class PublicJobSitemapResponse(BaseModel):
    items: list[PublicJobSitemapItem]
    next_after: UUID | None
    limit: int


class PublicJobDetail(PublicJobListItem):
    company: PublicCompanyDetail
    lifecycle_status: JobLifecycleStatus
    description: str | None
    source_url: PublicHttpUrl
    absence_first_detected_at: datetime | None
    no_longer_observed_at: datetime | None
    reappeared_at: datetime | None
