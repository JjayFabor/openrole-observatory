from datetime import datetime
from uuid import UUID

from app.jobs.lifecycle_errors import PresenceDataInvariantError
from app.jobs.models import Job


def validate_lifecycle_evidence_time(
    job: Job, pipeline_run_id: UUID, reconciliation_time: datetime
) -> None:
    for known_at in (
        job.last_seen_at,
        job.absence_first_detected_at,
        job.no_longer_observed_at,
        job.reappeared_at,
    ):
        if known_at is not None and known_at > reconciliation_time:
            raise PresenceDataInvariantError(
                pipeline_run_id,
                "run observation time predates the job's current evidence",
            )
