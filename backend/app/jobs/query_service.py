from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.companies.models import Company
from app.jobs.errors import (
    CurrentJobVersionInvariantError,
    CurrentJobVersionMissingError,
)
from app.jobs.models import (
    Job,
    JobChangeEvent,
    JobLifecycleEvent,
    JobLifecycleStatus,
    JobVersion,
)
from app.jobs.read_schemas import (
    CurrentJobVersionSummary,
    JobChangeList,
    JobChangeRead,
    JobCompanySummary,
    JobDetailRead,
    JobLifecycleEventRead,
    JobLifecycleRead,
    JobList,
    JobListItem,
    JobRead,
    JobSourceSummary,
    JobVersionList,
    JobVersionRead,
)
from app.sources.models import SourceConnection


class JobQueryService:
    """Read stored identity, canonical history, and lifecycle evidence."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        lifecycle_status: JobLifecycleStatus | None = None,
        source_connection_id: UUID | None = None,
        q: str | None = None,
    ) -> JobList:
        identity_filters = []
        if lifecycle_status is not None:
            identity_filters.append(Job.lifecycle_status == lifecycle_status.value)
        if source_connection_id is not None:
            identity_filters.append(Job.source_connection_id == source_connection_id)
        current_version = and_(
            JobVersion.job_id == Job.id, JobVersion.is_current.is_(True)
        )
        filters = list(identity_filters)
        search = q.strip() if q else ""
        if search:
            filters.append(
                or_(
                    JobVersion.title.icontains(search, autoescape=True),
                    JobVersion.location_text.icontains(search, autoescape=True),
                    Job.external_job_id.icontains(search, autoescape=True),
                )
            )

        async with self._session_factory() as session:
            # Check the identity scope before canonical search: a missing version
            # cannot be searched and must not quietly disappear from the dataset.
            missing_id = await session.scalar(
                select(Job.id)
                .outerjoin(JobVersion, current_version)
                .where(*identity_filters, JobVersion.id.is_(None))
                .limit(1)
            )
            if missing_id is not None:
                raise CurrentJobVersionMissingError(missing_id)
            total = await session.scalar(
                select(func.count(Job.id))
                .outerjoin(JobVersion, current_version)
                .where(*filters)
            )
            # Select only list fields. No lazy relationships or per-row queries;
            # the partial unique index permits at most one current version.
            rows = await session.execute(
                select(
                    Job.id,
                    Job.external_job_id,
                    Job.lifecycle_status,
                    Job.first_seen_at,
                    Job.last_seen_at,
                    Job.absence_first_detected_at,
                    Job.reappeared_at,
                    Job.consecutive_absent_runs,
                    Company.id.label("company_id"),
                    Company.name.label("company_name"),
                    SourceConnection.id.label("source_id"),
                    SourceConnection.provider,
                    JobVersion.id.label("version_id"),
                    JobVersion.version_number,
                    JobVersion.title,
                    JobVersion.location_text,
                    JobVersion.workplace_type,
                    JobVersion.employment_type,
                )
                .select_from(Job)
                .outerjoin(JobVersion, current_version)
                .join(Company, Company.id == Job.company_id)
                .join(SourceConnection, SourceConnection.id == Job.source_connection_id)
                .where(*filters)
                .order_by(Job.last_seen_at.desc(), Job.id.asc())
                .limit(limit)
                .offset(offset)
            )
            items = []
            for row in rows.mappings():
                if row["version_id"] is None:
                    raise CurrentJobVersionMissingError(row["id"])
                items.append(
                    JobListItem(
                        id=row["id"],
                        external_job_id=row["external_job_id"],
                        lifecycle_status=row["lifecycle_status"],
                        first_seen_at=row["first_seen_at"],
                        last_seen_at=row["last_seen_at"],
                        absence_first_detected_at=row["absence_first_detected_at"],
                        reappeared_at=row["reappeared_at"],
                        consecutive_absent_runs=row["consecutive_absent_runs"],
                        company=JobCompanySummary(
                            id=row["company_id"], name=row["company_name"]
                        ),
                        source=JobSourceSummary(
                            id=row["source_id"], provider=row["provider"]
                        ),
                        current_version=CurrentJobVersionSummary(
                            id=row["version_id"],
                            version_number=row["version_number"],
                            title=row["title"],
                            location_text=row["location_text"],
                            workplace_type=row["workplace_type"],
                            employment_type=row["employment_type"],
                        ),
                    )
                )
            return JobList(items=items, total=total or 0, limit=limit, offset=offset)

    async def get(self, job_id: UUID) -> JobDetailRead | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Job, JobVersion)
                .outerjoin(
                    JobVersion,
                    and_(JobVersion.job_id == Job.id, JobVersion.is_current.is_(True)),
                )
                .where(Job.id == job_id)
            )
            try:
                row = result.one_or_none()
            except MultipleResultsFound as error:
                raise CurrentJobVersionInvariantError(job_id) from error
            if row is None:
                return None
            job, version = row
            if version is None:
                raise CurrentJobVersionMissingError(job_id)
            return JobDetailRead(
                **JobRead.model_validate(job).model_dump(),
                current_version=JobVersionRead.model_validate(version),
            )

    async def versions(
        self, job_id: UUID, *, limit: int, offset: int
    ) -> JobVersionList | None:
        async with self._session_factory() as session:
            if await session.scalar(select(Job.id).where(Job.id == job_id)) is None:
                return None
            versions = await session.scalars(
                select(JobVersion)
                .where(JobVersion.job_id == job_id)
                .order_by(JobVersion.version_number.asc())
                .limit(limit)
                .offset(offset)
            )
            return JobVersionList(
                items=[JobVersionRead.model_validate(version) for version in versions],
                limit=limit,
                offset=offset,
            )

    async def changes(
        self, job_id: UUID, *, limit: int, offset: int
    ) -> JobChangeList | None:
        async with self._session_factory() as session:
            if await session.scalar(select(Job.id).where(Job.id == job_id)) is None:
                return None
            from_version = aliased(JobVersion)
            to_version = aliased(JobVersion)
            # Join scalar version numbers, without loading canonical descriptions
            # or accessing the event's lazy version relationships.
            rows = await session.execute(
                select(
                    JobChangeEvent.id,
                    JobChangeEvent.field_name,
                    JobChangeEvent.change_type,
                    JobChangeEvent.old_value,
                    JobChangeEvent.new_value,
                    JobChangeEvent.from_version_id,
                    JobChangeEvent.to_version_id,
                    JobChangeEvent.detected_at,
                    JobChangeEvent.created_at,
                    from_version.version_number.label("from_version_number"),
                    to_version.version_number.label("to_version_number"),
                )
                .join(from_version, from_version.id == JobChangeEvent.from_version_id)
                .join(to_version, to_version.id == JobChangeEvent.to_version_id)
                .where(JobChangeEvent.job_id == job_id)
                .order_by(
                    to_version.version_number.asc(),
                    JobChangeEvent.field_name.asc(),
                    JobChangeEvent.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
            return JobChangeList(
                items=[JobChangeRead.model_validate(row) for row in rows.mappings()],
                limit=limit,
                offset=offset,
            )

    async def lifecycle(
        self, job_id: UUID, *, limit: int, offset: int
    ) -> JobLifecycleRead | None:
        async with self._session_factory() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return None
            events = await session.scalars(
                select(JobLifecycleEvent)
                .where(JobLifecycleEvent.job_id == job_id)
                .order_by(
                    JobLifecycleEvent.occurred_at.asc(),
                    JobLifecycleEvent.created_at.asc(),
                    JobLifecycleEvent.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
            return JobLifecycleRead(
                job_id=job.id,
                current_status=JobLifecycleStatus(job.lifecycle_status),
                first_seen_at=job.first_seen_at,
                last_seen_at=job.last_seen_at,
                absence_first_detected_at=job.absence_first_detected_at,
                no_longer_observed_at=job.no_longer_observed_at,
                reappeared_at=job.reappeared_at,
                consecutive_absent_runs=job.consecutive_absent_runs,
                events=[
                    JobLifecycleEventRead.model_validate(event) for event in events
                ],
                limit=limit,
                offset=offset,
            )
