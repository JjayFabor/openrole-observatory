from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.pipeline_runs.models import PipelineRun
    from app.quarantine.models import QuarantineRecord
    from app.source_observations.models import SourceObservation


class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id"),
        UniqueConstraint("r2_object_key"),
        CheckConstraint(
            "content_length_bytes >= 0",
            name="content_length_bytes_non_negative",
        ),
        CheckConstraint(
            "record_count >= 0",
            name="record_count_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pipeline_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("pipeline_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    r2_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    content_length_bytes: Mapped[int | None] = mapped_column(BigInteger)
    record_count: Mapped[int | None] = mapped_column(Integer)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="raw_snapshot")
    source_observations: Mapped[list[SourceObservation]] = relationship(
        back_populates="raw_snapshot",
        passive_deletes=True,
    )
    quarantine_records: Mapped[list[QuarantineRecord]] = relationship(
        back_populates="raw_snapshot",
        passive_deletes=True,
    )
