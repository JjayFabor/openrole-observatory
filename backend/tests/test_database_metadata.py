from app.database.base import NAMING_CONVENTION, Base


def test_base_metadata_has_deterministic_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert NAMING_CONVENTION == {
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


def test_base_metadata_contains_phase_one_and_task_24_tables() -> None:
    from app.companies.models import Company
    from app.jobs.models import Job, JobChangeEvent, JobLifecycleEvent, JobVersion
    from app.pipeline_runs.models import PipelineRun
    from app.quarantine.models import QuarantineRecord
    from app.raw_snapshots.models import RawSnapshot
    from app.source_observations.models import SourceObservation
    from app.sources.models import SourceConnection

    assert Company.metadata is Base.metadata
    assert SourceConnection.metadata is Base.metadata
    assert PipelineRun.metadata is Base.metadata
    assert RawSnapshot.metadata is Base.metadata
    assert QuarantineRecord.metadata is Base.metadata
    assert Job.metadata is Base.metadata
    assert JobVersion.metadata is Base.metadata
    assert JobChangeEvent.metadata is Base.metadata
    assert JobLifecycleEvent.metadata is Base.metadata
    assert SourceObservation.metadata is Base.metadata
    assert "source_observation_id" in JobVersion.__table__.columns
    assert set(Base.metadata.tables) == {
        "companies",
        "source_connections",
        "pipeline_runs",
        "raw_snapshots",
        "jobs",
        "job_versions",
        "source_observations",
        "quarantine_records",
        "job_change_events",
        "job_lifecycle_events",
    }
