from app.companies.models import Company
from app.jobs.models import Job, JobChangeEvent, JobLifecycleEvent, JobVersion
from app.pipeline_runs.models import PipelineRun
from app.quarantine.models import QuarantineRecord
from app.raw_snapshots.models import RawSnapshot
from app.source_observations.models import SourceObservation
from app.sources.models import SourceConnection

REGISTERED_MODELS = (
    Company,
    SourceConnection,
    PipelineRun,
    RawSnapshot,
    QuarantineRecord,
    SourceObservation,
    Job,
    JobVersion,
    JobChangeEvent,
    JobLifecycleEvent,
)


def register_models() -> None:
    """Import every ORM model before SQLAlchemy configures relationships."""

    return None
