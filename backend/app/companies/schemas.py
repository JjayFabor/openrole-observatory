from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

NonEmptyString = Annotated[str, Field(min_length=1)]


class CompanyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString
    slug: NonEmptyString
    domain: NonEmptyString | None = None
    careers_url: HttpUrl | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    domain: str | None
    careers_url: HttpUrl | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
