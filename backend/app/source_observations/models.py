from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.jobs.models import JobVersion
    from app.pipeline_runs.models import PipelineRun
    from app.raw_snapshots.models import RawSnapshot
    from app.sources.models import SourceConnection


class SourceObservation(Base):
    __tablename__ = "source_observations"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_run_id",
            "external_job_id",
            name="uq_source_observations_pipeline_run_id_external_job_id",
        ),
        CheckConstraint(
            "source_content_hash IS NULL OR source_content_hash ~ '^[0-9a-f]{64}$'",
            name="source_content_hash_sha256",
        ),
        Index("ix_source_observations_raw_snapshot_id", "raw_snapshot_id"),
        Index(
            "ix_source_observations_source_connection_id_external_job_id",
            "source_connection_id",
            "external_job_id",
        ),
        Index("ix_source_observations_observed_at", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pipeline_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("pipeline_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_connection_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    raw_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_job_id: Mapped[str] = mapped_column(String, nullable=False)
    raw_record_locator: Mapped[str | None] = mapped_column(String)
    source_content_hash: Mapped[str | None] = mapped_column(CHAR(64))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pipeline_run: Mapped[PipelineRun] = relationship(
        back_populates="source_observations"
    )
    source_connection: Mapped[SourceConnection] = relationship(
        back_populates="source_observations"
    )
    raw_snapshot: Mapped[RawSnapshot] = relationship(
        back_populates="source_observations"
    )
    job_version: Mapped[JobVersion | None] = relationship(
        back_populates="source_observation",
        uselist=False,
        passive_deletes=True,
    )
