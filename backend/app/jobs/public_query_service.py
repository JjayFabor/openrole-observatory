from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import ColumnElement, RowMapping, Select, and_, case, func, or_, select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.companies.models import Company
from app.jobs.errors import (
    CurrentJobVersionInvariantError,
    CurrentJobVersionMissingError,
)
from app.jobs.models import Job, JobChangeEvent, JobLifecycleStatus, JobVersion
from app.jobs.public_change_projection import (
    PUBLIC_STORED_CHANGE_FIELDS,
    PUBLIC_TEXT_CHANGE_FIELDS,
    SALARY_CHANGE_FIELDS,
    StoredPublicChange,
    project_public_change_groups,
)
from app.jobs.public_change_schemas import PublicJobChangesResponse, PublicSalaryValue
from app.jobs.public_errors import PublicJobReadError
from app.jobs.public_read_schemas import (
    PublicCompanyDetail,
    PublicCompanySummary,
    PublicEmploymentFilter,
    PublicJobDetail,
    PublicJobListItem,
    PublicJobListResponse,
    PublicJobSitemapItem,
    PublicJobSitemapResponse,
    PublicJobSourceSummary,
    PublicWorkplaceFilter,
    validate_public_url,
)
from app.sources.models import SourceConnection


def _listing(row: RowMapping) -> PublicJobListItem:
    return PublicJobListItem(
        id=row["id"],
        title=row["title"],
        company=PublicCompanySummary(name=row["company_name"], domain=row["domain"]),
        location_text=row["location_text"],
        city=row["city"],
        region=row["region"],
        country_code=row["country_code"],
        workplace_type=row["workplace_type"],
        employment_type=row["employment_type"],
        salary_min=row["salary_min"],
        salary_max=row["salary_max"],
        salary_currency=row["salary_currency"],
        salary_period=row["salary_period"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        source=PublicJobSourceSummary(provider=row["provider"]),
    )


def _salary_context(row: RowMapping, side: str) -> PublicSalaryValue | None:
    values = {
        name: row[f"{side}_{name}"] for name in ("min", "max", "currency", "period")
    }
    if all(value is None for value in values.values()):
        return None
    return PublicSalaryValue(**values)


class PublicJobQueryService:
    """Project seeker-facing facts without loading operational ORM entities."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def sitemap(
        self,
        *,
        limit: int,
        after: UUID | None = None,
    ) -> PublicJobSitemapResponse:
        query = (
            select(Job.id, func.count(JobVersion.id).label("current_count"))
            .join(SourceConnection, SourceConnection.id == Job.source_connection_id)
            .outerjoin(JobVersion, self._current_version_join())
            .where(
                Job.lifecycle_status == JobLifecycleStatus.OBSERVED.value,
                SourceConnection.is_active.is_(True),
            )
            .group_by(Job.id)
            .order_by(Job.id.asc())
            .limit(limit + 1)
        )
        if after is not None:
            query = query.where(Job.id > after)
        async with self._session_factory() as session:
            rows = (await session.execute(query)).all()
            for row in rows:
                if row.current_count == 0:
                    raise CurrentJobVersionMissingError(row.id)
                if row.current_count != 1:
                    raise CurrentJobVersionInvariantError(row.id)
            items = [PublicJobSitemapItem(id=row.id) for row in rows[:limit]]
            return PublicJobSitemapResponse(
                items=items,
                next_after=items[-1].id if len(rows) > limit else None,
                limit=limit,
            )

    @staticmethod
    def _current_version_join() -> ColumnElement[bool]:
        return and_(JobVersion.job_id == Job.id, JobVersion.is_current.is_(True))

    @staticmethod
    def _listing_query() -> Select[*tuple[Any, ...]]:
        return (
            select(
                Job.id,
                Job.first_seen_at,
                Job.last_seen_at,
                JobVersion.id.label("version_id"),
                JobVersion.title,
                JobVersion.location_text,
                JobVersion.city,
                JobVersion.region,
                JobVersion.country_code,
                JobVersion.workplace_type,
                JobVersion.employment_type,
                JobVersion.salary_min,
                JobVersion.salary_max,
                JobVersion.salary_currency,
                JobVersion.salary_period,
                Company.name.label("company_name"),
                Company.domain,
                SourceConnection.provider,
            )
            .select_from(Job)
            .join(Company, Company.id == Job.company_id)
            .join(SourceConnection, SourceConnection.id == Job.source_connection_id)
            .outerjoin(JobVersion, PublicJobQueryService._current_version_join())
        )

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        q: str | None = None,
        location: str | None = None,
        workplace_type: PublicWorkplaceFilter | None = None,
        employment_type: PublicEmploymentFilter | None = None,
    ) -> PublicJobListResponse:
        eligibility = [
            Job.lifecycle_status == JobLifecycleStatus.OBSERVED.value,
            SourceConnection.is_active.is_(True),
        ]
        filters = list(eligibility)
        search = q.strip() if q else ""
        if search:
            filters.append(
                or_(
                    JobVersion.title.icontains(search, autoescape=True),
                    Company.name.icontains(search, autoescape=True),
                    JobVersion.location_text.icontains(search, autoescape=True),
                )
            )
        location_search = location.strip() if location else ""
        if location_search:
            filters.append(
                JobVersion.location_text.icontains(location_search, autoescape=True)
            )
        if workplace_type is not None:
            filters.append(JobVersion.workplace_type == workplace_type.value)
        if employment_type is not None:
            filters.append(JobVersion.employment_type == employment_type.value)

        async with self._session_factory() as session:
            # Check the eligible identity scope before content filters: missing
            # versions cannot match search and must not silently disappear.
            invalid = (
                await session.execute(
                    select(Job.id, func.count(JobVersion.id).label("current_count"))
                    .join(
                        SourceConnection,
                        SourceConnection.id == Job.source_connection_id,
                    )
                    .outerjoin(JobVersion, self._current_version_join())
                    .where(*eligibility)
                    .group_by(Job.id)
                    .having(func.count(JobVersion.id) != 1)
                    .limit(1)
                )
            ).one_or_none()
            if invalid is not None:
                if invalid.current_count == 0:
                    raise CurrentJobVersionMissingError(invalid.id)
                raise CurrentJobVersionInvariantError(invalid.id)

            query = self._listing_query().where(*filters)
            total = await session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            rows = await session.execute(
                query.order_by(Job.last_seen_at.desc(), Job.id.asc())
                .limit(limit)
                .offset(offset)
            )
            try:
                items = [_listing(row) for row in rows.mappings()]
            except ValidationError as error:
                raise PublicJobReadError from error
            return PublicJobListResponse(
                items=items, total=total or 0, limit=limit, offset=offset
            )

    async def get(self, job_id: UUID) -> PublicJobDetail | None:
        async with self._session_factory() as session:
            rows = await session.execute(
                self._listing_query()
                .add_columns(
                    Job.lifecycle_status,
                    Job.absence_first_detected_at,
                    Job.no_longer_observed_at,
                    Job.reappeared_at,
                    JobVersion.description,
                    JobVersion.source_url,
                    Company.careers_url,
                )
                .where(Job.id == job_id)
            )
            try:
                row = rows.mappings().one_or_none()
            except MultipleResultsFound as error:
                raise CurrentJobVersionInvariantError(job_id) from error
            if row is None:
                return None
            if row["version_id"] is None:
                raise CurrentJobVersionMissingError(job_id)

            careers_url = row["careers_url"]
            if careers_url is not None:
                try:
                    validate_public_url(careers_url)
                except ValueError:
                    # This optional company link must not make a usable listing
                    # inaccessible if older stored data bypassed input validation.
                    careers_url = None
            try:
                listing = _listing(row)
                return PublicJobDetail(
                    **listing.model_dump(exclude={"company"}),
                    company=PublicCompanyDetail(
                        name=row["company_name"],
                        domain=row["domain"],
                        careers_url=careers_url,
                    ),
                    lifecycle_status=row["lifecycle_status"],
                    description=row["description"],
                    source_url=row["source_url"],
                    absence_first_detected_at=row["absence_first_detected_at"],
                    no_longer_observed_at=row["no_longer_observed_at"],
                    reappeared_at=row["reappeared_at"],
                )
            except ValidationError as error:
                raise PublicJobReadError from error

    async def changes(
        self,
        job_id: UUID,
        *,
        limit: int,
    ) -> PublicJobChangesResponse | None:
        async with self._session_factory() as session:
            if await session.scalar(select(Job.id).where(Job.id == job_id)) is None:
                return None

            events = JobChangeEvent
            allowed = events.field_name.in_(PUBLIC_STORED_CHANGE_FIELDS)
            # Bound complete curated transitions, so omitted churn cannot consume
            # the limit and a salary update cannot be cut into partial field rows.
            groups = (
                select(
                    events.from_version_id,
                    events.to_version_id,
                    func.max(events.detected_at).label("observed_at"),
                )
                .where(events.job_id == job_id, allowed)
                .group_by(events.from_version_id, events.to_version_id)
                .order_by(
                    func.max(events.detected_at).desc(),
                    events.to_version_id.desc(),
                    events.from_version_id.desc(),
                )
                .limit(limit)
                .subquery()
            )
            before = aliased(JobVersion)
            after = aliased(JobVersion)
            salary_event = events.field_name.in_(SALARY_CHANGE_FIELDS)
            text_event = events.field_name.in_(PUBLIC_TEXT_CHANGE_FIELDS)
            rows = await session.execute(
                select(
                    events.from_version_id,
                    events.to_version_id,
                    events.detected_at,
                    events.field_name,
                    events.change_type,
                    # Historical description bodies never enter this read result.
                    case((text_event, events.old_value), else_=None).label("old_value"),
                    case((text_event, events.new_value), else_=None).label("new_value"),
                    before.id.label("before_id"),
                    after.id.label("after_id"),
                    before.salary_min.label("old_min"),
                    before.salary_max.label("old_max"),
                    before.salary_currency.label("old_currency"),
                    before.salary_period.label("old_period"),
                    after.salary_min.label("new_min"),
                    after.salary_max.label("new_max"),
                    after.salary_currency.label("new_currency"),
                    after.salary_period.label("new_period"),
                )
                .join(
                    groups,
                    and_(
                        groups.c.from_version_id == events.from_version_id,
                        groups.c.to_version_id == events.to_version_id,
                    ),
                )
                .outerjoin(
                    before,
                    and_(
                        before.id == events.from_version_id,
                        before.job_id == job_id,
                        salary_event,
                    ),
                )
                .outerjoin(
                    after,
                    and_(
                        after.id == events.to_version_id,
                        after.job_id == job_id,
                        salary_event,
                    ),
                )
                .where(events.job_id == job_id, allowed)
                .order_by(
                    groups.c.observed_at.desc(),
                    groups.c.to_version_id.desc(),
                    groups.c.from_version_id.desc(),
                    events.field_name.asc(),
                )
            )
            try:
                records: list[StoredPublicChange] = []
                for row in rows.mappings():
                    is_salary = row["field_name"] in SALARY_CHANGE_FIELDS
                    if is_salary and (
                        row["before_id"] is None or row["after_id"] is None
                    ):
                        raise ValueError("Salary context does not belong to this job.")
                    records.append(
                        StoredPublicChange(
                            from_version_id=row["from_version_id"],
                            to_version_id=row["to_version_id"],
                            detected_at=row["detected_at"],
                            field_name=row["field_name"],
                            change_type=row["change_type"],
                            old_value=row["old_value"],
                            new_value=row["new_value"],
                            old_salary=_salary_context(row, "old")
                            if is_salary
                            else None,
                            new_salary=_salary_context(row, "new")
                            if is_salary
                            else None,
                        )
                    )
                return PublicJobChangesResponse(
                    job_id=job_id,
                    items=project_public_change_groups(records),
                    limit=limit,
                )
            except ValueError as error:
                raise PublicJobReadError from error
