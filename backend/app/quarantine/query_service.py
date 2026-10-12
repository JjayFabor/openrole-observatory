from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.companies.models import Company
from app.quarantine.models import QuarantineRecord, QuarantineStatus
from app.quarantine.read_schemas import (
    QuarantineList,
    QuarantineListItem,
    QuarantineRecordDetail,
)
from app.sources.models import SourceConnection


class QuarantineQueryService:
    """Read persisted diagnostics and lineage without loading Bronze payloads."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        status: QuarantineStatus | None = None,
        pipeline_run_id: UUID | None = None,
        source_connection_id: UUID | None = None,
        error_category: str | None = None,
    ) -> QuarantineList:
        filters = []
        if status is not None:
            filters.append(QuarantineRecord.status == status.value)
        if pipeline_run_id is not None:
            filters.append(QuarantineRecord.pipeline_run_id == pipeline_run_id)
        if source_connection_id is not None:
            filters.append(
                QuarantineRecord.source_connection_id == source_connection_id
            )
        category = error_category.strip() if error_category else ""
        if category:
            filters.append(QuarantineRecord.error_category == category)

        async with self._session_factory() as session:
            total = await session.scalar(
                select(func.count(QuarantineRecord.id)).where(*filters)
            )
            # Scalar projection avoids JSON details on the list and lazy source
            # relationships. The same predicates apply before count/pagination.
            rows = await session.execute(
                select(
                    QuarantineRecord.id,
                    QuarantineRecord.pipeline_run_id,
                    QuarantineRecord.source_connection_id,
                    QuarantineRecord.raw_snapshot_id,
                    QuarantineRecord.external_job_id,
                    QuarantineRecord.raw_record_locator,
                    QuarantineRecord.error_category,
                    QuarantineRecord.error_code,
                    QuarantineRecord.error_message,
                    QuarantineRecord.status,
                    QuarantineRecord.created_at,
                    QuarantineRecord.resolved_at,
                    SourceConnection.provider,
                    Company.name.label("company_name"),
                )
                .select_from(QuarantineRecord)
                .join(
                    SourceConnection,
                    SourceConnection.id == QuarantineRecord.source_connection_id,
                )
                .join(Company, Company.id == SourceConnection.company_id)
                .where(*filters)
                .order_by(
                    QuarantineRecord.created_at.desc(), QuarantineRecord.id.desc()
                )
                .limit(limit)
                .offset(offset)
            )
            return QuarantineList(
                items=[
                    QuarantineListItem.model_validate(
                        {
                            **row,
                            "source": {
                                "provider": row["provider"],
                                "company_name": row["company_name"],
                            },
                        }
                    )
                    for row in rows.mappings()
                ],
                total=total or 0,
                limit=limit,
                offset=offset,
            )

    async def get(self, record_id: UUID) -> QuarantineRecordDetail | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(QuarantineRecord, SourceConnection.provider, Company.name)
                .join(
                    SourceConnection,
                    SourceConnection.id == QuarantineRecord.source_connection_id,
                )
                .join(Company, Company.id == SourceConnection.company_id)
                .where(QuarantineRecord.id == record_id)
            )
            row = result.one_or_none()
            if row is None:
                return None
            record, provider, company_name = row
            return QuarantineRecordDetail.model_validate(
                {
                    "id": record.id,
                    "pipeline_run_id": record.pipeline_run_id,
                    "source_connection_id": record.source_connection_id,
                    "raw_snapshot_id": record.raw_snapshot_id,
                    "external_job_id": record.external_job_id,
                    "raw_record_locator": record.raw_record_locator,
                    "error_category": record.error_category,
                    "error_code": record.error_code,
                    "error_message": record.error_message,
                    "error_details": record.error_details,
                    "status": record.status,
                    "created_at": record.created_at,
                    "resolved_at": record.resolved_at,
                    "source": {"provider": provider, "company_name": company_name},
                }
            )
