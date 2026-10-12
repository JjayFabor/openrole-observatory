from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.jobs.models import Job, JobLifecycleEvent, JobLifecycleStatus
from app.jobs.presence import PresenceSetResult
from app.jobs.presence_service import PresenceSetBuilder
from app.pipeline_runs.models import PipelineRun, PipelineRunStatus
from app.quarantine.models import QuarantineRecord
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.models import SourceConnection
from tests.test_changed_job_persistence import DatabaseContext, create_source

FIRST_SEEN_AT = datetime(2026, 10, 1, 12, tzinfo=UTC)
FIRST_ABSENCE_AT = datetime(2026, 10, 3, 12, tzinfo=UTC)
CONFIRMED_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 10, 8, 12, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class PresenceRunSetup:
    source: SourceConnection
    run: PipelineRun
    snapshot: RawSnapshot
    observations: tuple[SourceObservation, ...]
    quarantines: tuple[QuarantineRecord, ...]


async def create_presence_run(
    context: DatabaseContext,
    *,
    source: SourceConnection | None = None,
    observations: Sequence[tuple[str, str | None]] = (),
    quarantines: Sequence[tuple[str | None, str | None]] = (),
    records_valid: int | None = None,
    status: PipelineRunStatus | None = None,
    retrieved_at: datetime = RETRIEVED_AT,
) -> PresenceRunSetup:
    source = source or await create_source(context.session_factory)
    valid_count = len(observations) if records_valid is None else records_valid
    final_status = status or (
        PipelineRunStatus.COMPLETED_WITH_ERRORS
        if quarantines
        else PipelineRunStatus.COMPLETED
    )
    async with context.session_factory.begin() as session:
        pipeline_run = PipelineRun(
            source_connection_id=source.id,
            status=final_status.value,
            started_at=retrieved_at - timedelta(minutes=1),
            completed_at=(
                retrieved_at + timedelta(hours=1)
                if final_status
                in {
                    PipelineRunStatus.COMPLETED,
                    PipelineRunStatus.COMPLETED_WITH_ERRORS,
                }
                else None
            ),
            records_fetched=valid_count + len(quarantines),
            records_valid=valid_count,
            records_quarantined=len(quarantines),
            jobs_new=valid_count,
        )
        snapshot = RawSnapshot(
            pipeline_run=pipeline_run,
            r2_object_key=f"bronze/tests/presence/{uuid4().hex}/jobs.json",
            content_hash="a" * 64,
            content_type="application/json",
            content_length_bytes=100,
            record_count=valid_count + len(quarantines),
            retrieved_at=retrieved_at,
        )
        observed_rows = tuple(
            SourceObservation(
                pipeline_run=pipeline_run,
                source_connection_id=source.id,
                raw_snapshot=snapshot,
                external_job_id=external_id,
                raw_record_locator=locator,
                observed_at=retrieved_at,
            )
            for external_id, locator in observations
        )
        quarantined_rows = tuple(
            QuarantineRecord(
                pipeline_run=pipeline_run,
                source_connection_id=source.id,
                raw_snapshot=snapshot,
                external_job_id=external_id,
                raw_record_locator=locator,
                error_category="record_validation_failed",
                error_message="fixture processing failure",
            )
            for external_id, locator in quarantines
        )
        session.add_all([pipeline_run, snapshot, *observed_rows, *quarantined_rows])
        await session.flush()
    return PresenceRunSetup(
        source, pipeline_run, snapshot, observed_rows, quarantined_rows
    )


async def build_presence(
    context: DatabaseContext, pipeline_run_id: UUID
) -> PresenceSetResult:
    async with context.session_factory() as session:
        return await PresenceSetBuilder(session).build_presence_set(pipeline_run_id)


async def create_lifecycle_job(
    context: DatabaseContext,
    source: SourceConnection,
    external_id: str,
    *,
    status: JobLifecycleStatus = JobLifecycleStatus.OBSERVED,
    absence_count: int = 0,
    absence_first_at: datetime | None = None,
    confirmed_at: datetime | None = None,
    reappeared_at: datetime | None = None,
) -> Job:
    async with context.session_factory.begin() as session:
        job = Job(
            company_id=source.company_id,
            source_connection_id=source.id,
            external_job_id=external_id,
            first_seen_at=FIRST_SEEN_AT,
            last_seen_at=FIRST_SEEN_AT,
            lifecycle_status=status.value,
            consecutive_absent_runs=absence_count,
            absence_first_detected_at=absence_first_at,
            no_longer_observed_at=confirmed_at,
            reappeared_at=reappeared_at,
        )
        session.add(job)
        await session.flush()
    return job


def lifecycle_state(job: Job) -> tuple[object, ...]:
    return (
        job.first_seen_at,
        job.last_seen_at,
        job.lifecycle_status,
        job.consecutive_absent_runs,
        job.absence_first_detected_at,
        job.no_longer_observed_at,
        job.reappeared_at,
    )


async def load_lifecycle_events(
    context: DatabaseContext, run_id: UUID
) -> list[JobLifecycleEvent]:
    async with context.session_factory() as session:
        return list(
            await session.scalars(
                select(JobLifecycleEvent).where(
                    JobLifecycleEvent.pipeline_run_id == run_id
                )
            )
        )
