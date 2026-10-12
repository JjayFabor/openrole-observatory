from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.companies.models import Company
from app.pipeline_runs.models import PipelineRun
from app.pipeline_runs.schemas import PipelineRunRead
from app.sources.models import SourceConnection, SourceProvider
from app.sources.read_schemas import SourceListItem, SourceListRead


class SourceQueryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        is_active: bool | None = None,
        provider: SourceProvider | None = None,
    ) -> SourceListRead:
        filters: list[ColumnElement[bool]] = []
        if is_active is not None:
            filters.append(SourceConnection.is_active == is_active)
        if provider is not None:
            filters.append(SourceConnection.provider == provider.value)
        async with self._session_factory() as session:
            total = await session.scalar(
                select(func.count(SourceConnection.id)).where(*filters)
            )
            items = await _read_sources(session, filters, limit=limit, offset=offset)
            return SourceListRead(
                items=items, total=total or 0, limit=limit, offset=offset
            )

    async def get(self, source_id: UUID) -> SourceListItem | None:
        async with self._session_factory() as session:
            items = await _read_sources(
                session, [SourceConnection.id == source_id], limit=1, offset=0
            )
            return items[0] if items else None


async def _read_sources(
    session: AsyncSession,
    filters: list[ColumnElement[bool]],
    *,
    limit: int,
    offset: int,
) -> list[SourceListItem]:
    # LIMIT 1 is evaluated per source inside the SQL statement, not as a
    # separate application query per row. Ties use the persisted run UUID.
    latest_run_id = (
        select(PipelineRun.id)
        .where(PipelineRun.source_connection_id == SourceConnection.id)
        .order_by(PipelineRun.started_at.desc(), PipelineRun.id.desc())
        .limit(1)
        .correlate(SourceConnection)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(
            SourceConnection.id,
            SourceConnection.company_id,
            SourceConnection.provider,
            SourceConnection.is_active,
            SourceConnection.last_attempted_sync_at,
            SourceConnection.last_successful_sync_at,
            Company.name.label("company_name"),
            Company.domain.label("company_domain"),
            Company.careers_url,
            PipelineRun,
        )
        .select_from(SourceConnection)
        .join(Company, Company.id == SourceConnection.company_id)
        .outerjoin(PipelineRun, PipelineRun.id == latest_run_id)
        .where(*filters)
        .order_by(Company.name.asc(), SourceConnection.id.asc())
        .limit(limit)
        .offset(offset)
    )
    items: list[SourceListItem] = []
    for row in rows.mappings():
        run = row["PipelineRun"]
        items.append(
            SourceListItem.model_validate(
                {
                    "id": row["id"],
                    "company_id": row["company_id"],
                    "provider": row["provider"],
                    "is_active": row["is_active"],
                    "last_attempted_sync_at": row["last_attempted_sync_at"],
                    "last_successful_sync_at": row["last_successful_sync_at"],
                    "company": {
                        "id": row["company_id"],
                        "name": row["company_name"],
                        "domain": row["company_domain"],
                        "careers_url": row["careers_url"],
                    },
                    "latest_run": PipelineRunRead.model_validate(run)
                    if run is not None
                    else None,
                }
            )
        )
    return items
