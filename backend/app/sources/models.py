from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.companies.models import Company
    from app.jobs.models import Job
    from app.pipeline_runs.models import PipelineRun
    from app.quarantine.models import QuarantineRecord
    from app.source_observations.models import SourceObservation


class SourceProvider(StrEnum):
    GREENHOUSE = "greenhouse"


class SourceConnection(Base):
    __tablename__ = "source_connections"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_account_key",
            name="uq_source_connections_provider_external_account_key",
        ),
        Index("ix_source_connections_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    external_account_key: Mapped[str] = mapped_column(String, nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_attempted_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    company: Mapped[Company] = relationship(back_populates="source_connections")
    pipeline_runs: Mapped[list[PipelineRun]] = relationship(
        back_populates="source_connection",
        passive_deletes=True,
    )
    jobs: Mapped[list[Job]] = relationship(
        back_populates="source_connection",
        passive_deletes=True,
    )
    source_observations: Mapped[list[SourceObservation]] = relationship(
        back_populates="source_connection",
        passive_deletes=True,
    )
    quarantine_records: Mapped[list[QuarantineRecord]] = relationship(
        back_populates="source_connection",
        passive_deletes=True,
    )
