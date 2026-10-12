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
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.pipeline_runs.models import PipelineRun
    from app.raw_snapshots.models import RawSnapshot
    from app.sources.models import SourceConnection


class QuarantineStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class QuarantineRecord(Base):
    __tablename__ = "quarantine_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved')",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL)",
            name="status_resolved_at_consistent",
        ),
        Index("ix_quarantine_records_pipeline_run_id", "pipeline_run_id"),
        Index("ix_quarantine_records_source_connection_id", "source_connection_id"),
        Index("ix_quarantine_records_raw_snapshot_id", "raw_snapshot_id"),
        Index("ix_quarantine_records_status", "status"),
        Index("ix_quarantine_records_error_category", "error_category"),
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
    external_job_id: Mapped[str | None] = mapped_column(String)
    raw_record_locator: Mapped[str | None] = mapped_column(String)
    error_category: Mapped[str] = mapped_column(String, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    error_details: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=QuarantineStatus.OPEN.value,
        server_default=text("'open'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pipeline_run: Mapped[PipelineRun] = relationship(
        back_populates="quarantine_records"
    )
    source_connection: Mapped[SourceConnection] = relationship(
        back_populates="quarantine_records"
    )
    raw_snapshot: Mapped[RawSnapshot] = relationship(
        back_populates="quarantine_records"
    )
