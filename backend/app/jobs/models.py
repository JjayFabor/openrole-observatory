from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.jobs.changes import FieldChangeType as FieldChangeType

if TYPE_CHECKING:
    from app.companies.models import Company
    from app.pipeline_runs.models import PipelineRun
    from app.source_observations.models import SourceObservation
    from app.sources.models import SourceConnection


class JobLifecycleStatus(StrEnum):
    OBSERVED = "observed"
    NOT_OBSERVED = "not_observed"


class JobLifecycleEventType(StrEnum):
    ABSENCE_DETECTED = "absence_detected"
    NOT_OBSERVED_CONFIRMED = "not_observed_confirmed"
    REAPPEARED = "reappeared"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "source_connection_id",
            "external_job_id",
            name="uq_jobs_source_connection_id_external_job_id",
        ),
        CheckConstraint(
            "last_seen_at >= first_seen_at",
            name="last_seen_at_not_before_first_seen_at",
        ),
        CheckConstraint(
            "consecutive_absent_runs >= 0",
            name="consecutive_absent_runs_non_negative",
        ),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_last_seen_at", "last_seen_at"),
        Index("ix_jobs_lifecycle_status", "lifecycle_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_connection_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_job_id: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=JobLifecycleStatus.OBSERVED.value,
        server_default=text("'observed'"),
    )
    no_longer_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reappeared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_absent_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    absence_first_detected_at: Mapped[datetime | None] = mapped_column(
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

    company: Mapped[Company] = relationship(back_populates="jobs")
    source_connection: Mapped[SourceConnection] = relationship(back_populates="jobs")
    versions: Mapped[list[JobVersion]] = relationship(
        back_populates="job",
        order_by="JobVersion.version_number",
        passive_deletes=True,
    )
    change_events: Mapped[list[JobChangeEvent]] = relationship(
        back_populates="job",
        passive_deletes=True,
    )
    lifecycle_events: Mapped[list[JobLifecycleEvent]] = relationship(
        back_populates="job",
        passive_deletes=True,
    )


class JobVersion(Base):
    __tablename__ = "job_versions"
    __table_args__ = (
        UniqueConstraint(
            "source_observation_id",
            name="uq_job_versions_source_observation_id",
        ),
        UniqueConstraint(
            "job_id",
            "version_number",
            name="uq_job_versions_job_id_version_number",
        ),
        UniqueConstraint(
            "job_id",
            "content_hash",
            name="uq_job_versions_job_id_content_hash",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="version_number_positive",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="content_hash_sha256",
        ),
        CheckConstraint(
            "salary_min IS NULL OR salary_min >= 0",
            name="salary_min_non_negative",
        ),
        CheckConstraint(
            "salary_max IS NULL OR salary_max >= 0",
            name="salary_max_non_negative",
        ),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_range_ordered",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="effective_range_ordered",
        ),
        CheckConstraint(
            "(is_current AND effective_to IS NULL) OR "
            "(NOT is_current AND effective_to IS NOT NULL)",
            name="current_effective_to_consistent",
        ),
        Index(
            "uq_job_versions_current",
            "job_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_observation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_observations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    country_code: Mapped[str | None] = mapped_column(CHAR(2))
    workplace_type: Mapped[str | None] = mapped_column(String)
    employment_type: Mapped[str | None] = mapped_column(String)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(CHAR(3))
    salary_period: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    canonical_metadata: Mapped[dict[str, object]] = mapped_column(
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

    job: Mapped[Job] = relationship(back_populates="versions")
    source_observation: Mapped[SourceObservation] = relationship(
        back_populates="job_version"
    )
    outgoing_change_events: Mapped[list[JobChangeEvent]] = relationship(
        back_populates="from_version",
        foreign_keys="JobChangeEvent.from_version_id",
        passive_deletes=True,
    )
    incoming_change_events: Mapped[list[JobChangeEvent]] = relationship(
        back_populates="to_version",
        foreign_keys="JobChangeEvent.to_version_id",
        passive_deletes=True,
    )


class JobChangeEvent(Base):
    """Historical explanation of one field difference between canonical versions."""

    __tablename__ = "job_change_events"
    __table_args__ = (
        UniqueConstraint(
            "from_version_id",
            "to_version_id",
            "field_name",
            name="uq_job_change_events_from_to_field",
        ),
        Index("ix_job_change_events_job_id_detected_at", "job_id", "detected_at"),
        Index("ix_job_change_events_to_version_id", "to_version_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    from_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("job_versions.id", ondelete="RESTRICT"), nullable=False
    )
    to_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("job_versions.id", ondelete="RESTRICT"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    # None means SQL NULL; use JSON.NULL explicitly to represent a JSON null value.
    old_value: Mapped[JsonValue] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    new_value: Mapped[JsonValue] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="change_events")
    from_version: Mapped[JobVersion] = relationship(
        back_populates="outgoing_change_events",
        foreign_keys=[from_version_id],
    )
    to_version: Mapped[JobVersion] = relationship(
        back_populates="incoming_change_events",
        foreign_keys=[to_version_id],
    )


class JobLifecycleEvent(Base):
    """Historical lifecycle evidence linked to the synchronization that caused it."""

    __tablename__ = "job_lifecycle_events"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "pipeline_run_id",
            "event_type",
            name="uq_job_lifecycle_events_job_run_type",
        ),
        Index("ix_job_lifecycle_events_job_id_occurred_at", "job_id", "occurred_at"),
        Index("ix_job_lifecycle_events_pipeline_run_id", "pipeline_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    pipeline_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("pipeline_runs.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    previous_status: Mapped[str | None] = mapped_column(String)
    new_status: Mapped[str | None] = mapped_column(String)
    event_metadata: Mapped[dict[str, JsonValue]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="lifecycle_events")
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="lifecycle_events")
