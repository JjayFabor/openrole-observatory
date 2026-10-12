from uuid import UUID

from pydantic import BaseModel

from app.sources.schemas import SourceHealthRead


class SourceCompanyRead(BaseModel):
    id: UUID
    name: str
    domain: str | None
    careers_url: str | None


class SourceListItem(SourceHealthRead):
    """Safe source identity and operational state shared by list and detail."""

    company: SourceCompanyRead


class SourceListRead(BaseModel):
    items: list[SourceListItem]
    total: int
    limit: int
    offset: int
