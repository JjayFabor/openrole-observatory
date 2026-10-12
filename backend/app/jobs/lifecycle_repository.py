from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import (
    Job,
    JobLifecycleEvent,
    JobLifecycleEventType,
    JobLifecycleStatus,
)
from app.raw_snapshots.models import RawSnapshot


class JobLifecycleRepository:
    """Operations needed for one atomic lifecycle reconciliation batch."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_reconciliation_time(self, pipeline_run_id: UUID) -> datetime | None:
        return await self._session.scalar(
            select(RawSnapshot.retrieved_at).where(
                RawSnapshot.pipeline_run_id == pipeline_run_id
            )
        )

    async def list_present_jobs_for_update(
        self, source_connection_id: UUID, present_external_job_ids: frozenset[str]
    ) -> list[Job]:
        if not present_external_job_ids:
            return []
        return list(
            await self._session.scalars(
                select(Job)
                .where(
                    Job.source_connection_id == source_connection_id,
                    Job.external_job_id.in_(present_external_job_ids),
                )
                .order_by(Job.id)
                .with_for_update()
            )
        )

    async def list_observed_jobs_for_update(
        self, source_connection_id: UUID
    ) -> list[Job]:
        return list(
            await self._session.scalars(
                select(Job)
                .where(
                    Job.source_connection_id == source_connection_id,
                    Job.lifecycle_status == JobLifecycleStatus.OBSERVED.value,
                )
                .order_by(Job.id)
                .with_for_update()
            )
        )

    async def list_absence_confirmation_jobs_for_update(
        self, source_connection_id: UUID
    ) -> list[Job]:
        return list(
            await self._session.scalars(
                select(Job)
                .where(
                    Job.source_connection_id == source_connection_id,
                    Job.lifecycle_status == JobLifecycleStatus.OBSERVED.value,
                    Job.consecutive_absent_runs >= 1,
                )
                .order_by(Job.id)
                .with_for_update()
            )
        )

    async def get_jobs_with_absence_events_for_run(
        self, source_connection_id: UUID, pipeline_run_id: UUID
    ) -> frozenset[UUID]:
        return frozenset(
            await self._session.scalars(
                select(JobLifecycleEvent.job_id)
                .join(Job, Job.id == JobLifecycleEvent.job_id)
                .where(
                    Job.source_connection_id == source_connection_id,
                    JobLifecycleEvent.pipeline_run_id == pipeline_run_id,
                    JobLifecycleEvent.event_type.in_(
                        (
                            JobLifecycleEventType.ABSENCE_DETECTED.value,
                            JobLifecycleEventType.NOT_OBSERVED_CONFIRMED.value,
                        )
                    ),
                )
            )
        )

    async def add_lifecycle_events(self, events: Sequence[JobLifecycleEvent]) -> None:
        self._session.add_all(events)
        await self._session.flush()
