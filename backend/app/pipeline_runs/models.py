from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.jobs.models import JobLifecycleEvent
    from app.quarantine.models import QuarantineRecord
    from app.raw_snapshots.models import RawSnapshot
    from app.source_observations.models import SourceObservation
    from app.sources.models import SourceConnection


class PipelineRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "records_fetched >= 0",
            name="records_fetched_non_negative",
        ),
        CheckConstraint(
            "records_valid >= 0",
            name="records_valid_non_negative",
        ),
        CheckConstraint(
            "records_quarantined >= 0",
            name="records_quarantined_non_negative",
        ),
        CheckConstraint("jobs_new >= 0", name="jobs_new_non_negative"),
        CheckConstraint("jobs_changed >= 0", name="jobs_changed_non_negative"),
        CheckConstraint(
            "jobs_unchanged >= 0",
            name="jobs_unchanged_non_negative",
        ),
        Index(
            "ix_pipeline_runs_source_connection_id_started_at",
            "source_connection_id",
            "started_at",
        ),
        Index("ix_pipeline_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_connection_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_fetched: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    records_valid: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    records_quarantined: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    jobs_new: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    jobs_changed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    jobs_unchanged: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_code: Mapped[str | None] = mapped_column(String)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    source_connection: Mapped[SourceConnection] = relationship(
        back_populates="pipeline_runs"
    )
    raw_snapshot: Mapped[RawSnapshot | None] = relationship(
        back_populates="pipeline_run",
        uselist=False,
        passive_deletes=True,
    )
    source_observations: Mapped[list[SourceObservation]] = relationship(
        back_populates="pipeline_run",
        passive_deletes=True,
    )
    quarantine_records: Mapped[list[QuarantineRecord]] = relationship(
        back_populates="pipeline_run",
        passive_deletes=True,
    )
    lifecycle_events: Mapped[list[JobLifecycleEvent]] = relationship(
        back_populates="pipeline_run",
        passive_deletes=True,
    )
