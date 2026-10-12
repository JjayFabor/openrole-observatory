from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.jobs.models import Job, JobChangeEvent, JobVersion
from app.pipeline_runs.models import PipelineRun
from app.source_observations.models import SourceObservation
from app.sources.models import SourceConnection


@dataclass(frozen=True, slots=True)
class JobObservationContext:
    observation: SourceObservation
    pipeline_run: PipelineRun
    source_connection: SourceConnection
    company: Company


class JobRepository:
    """Persistence operations required by job-observation application paths."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_observation_context(
        self,
        source_observation_id: UUID,
        *,
        for_update: bool = False,
    ) -> JobObservationContext | None:
        statement = (
            select(SourceObservation, PipelineRun, SourceConnection, Company)
            .join(
                PipelineRun,
                PipelineRun.id == SourceObservation.pipeline_run_id,
            )
            .join(
                SourceConnection,
                SourceConnection.id == SourceObservation.source_connection_id,
            )
            .join(Company, Company.id == SourceConnection.company_id)
            .where(SourceObservation.id == source_observation_id)
        )
        if for_update:
            statement = statement.with_for_update(of=SourceObservation)

        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None

        observation, pipeline_run, source_connection, company = row
        return JobObservationContext(
            observation=observation,
            pipeline_run=pipeline_run,
            source_connection=source_connection,
            company=company,
        )

    async def get_by_source_identity(
        self,
        source_connection_id: UUID,
        external_job_id: str,
        *,
        for_update: bool = False,
    ) -> Job | None:
        statement = select(Job).where(
            Job.source_connection_id == source_connection_id,
            Job.external_job_id == external_job_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_current_version(
        self,
        job_id: UUID,
        *,
        for_update: bool = False,
    ) -> JobVersion | None:
        statement = select(JobVersion).where(
            JobVersion.job_id == job_id,
            JobVersion.is_current.is_(True),
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.scalars(statement)).one_or_none()

    async def get_version_by_content_hash(
        self,
        job_id: UUID,
        content_hash: str,
    ) -> JobVersion | None:
        return await self._session.scalar(
            select(JobVersion).where(
                JobVersion.job_id == job_id,
                JobVersion.content_hash == content_hash,
            )
        )

    async def get_version_by_source_observation(
        self,
        source_observation_id: UUID,
    ) -> JobVersion | None:
        return await self._session.scalar(
            select(JobVersion).where(
                JobVersion.source_observation_id == source_observation_id
            )
        )

    async def add_job(self, job: Job) -> Job:
        self._session.add(job)
        await self._session.flush()
        return job

    async def add_version(self, version: JobVersion) -> JobVersion:
        self._session.add(version)
        await self._session.flush()
        return version

    async def add_change_events(self, events: Sequence[JobChangeEvent]) -> None:
        self._session.add_all(events)
        await self._session.flush()

    async def advance_last_seen_at(
        self,
        job: Job,
        observed_at: datetime,
    ) -> None:
        job.last_seen_at = max(job.last_seen_at, observed_at)
        await self._session.flush()

    async def flush(self) -> None:
        await self._session.flush()
