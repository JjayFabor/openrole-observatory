"""add job change and lifecycle schema

Revision ID: 55c52c19c673
Revises: 3e7f3cd24003
Create Date: 2026-10-08 16:18:45.013406

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers used by Alembic.
revision: str = "55c52c19c673"
down_revision: str | Sequence[str] | None = "3e7f3cd24003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision's schema changes."""
    # PostgreSQL fills existing rows with 0; retain the default for future inserts.
    op.add_column(
        "jobs",
        sa.Column(
            "consecutive_absent_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "absence_first_detected_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_check_constraint(
        op.f("ck_jobs_consecutive_absent_runs_non_negative"),
        "jobs",
        "consecutive_absent_runs >= 0",
    )
    op.create_table(
        "job_lifecycle_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_lifecycle_events_job_id_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            name=op.f("fk_job_lifecycle_events_pipeline_run_id_pipeline_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_lifecycle_events")),
        sa.UniqueConstraint(
            "job_id",
            "pipeline_run_id",
            "event_type",
            name="uq_job_lifecycle_events_job_run_type",
        ),
    )
    op.create_index(
        "ix_job_lifecycle_events_job_id_occurred_at",
        "job_lifecycle_events",
        ["job_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_lifecycle_events_pipeline_run_id",
        "job_lifecycle_events",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_table(
        "job_change_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("from_version_id", sa.Uuid(), nullable=False),
        sa.Column("to_version_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("change_type", sa.String(), nullable=False),
        sa.Column(
            "old_value",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "new_value",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["from_version_id"],
            ["job_versions.id"],
            name=op.f("fk_job_change_events_from_version_id_job_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_change_events_job_id_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_version_id"],
            ["job_versions.id"],
            name=op.f("fk_job_change_events_to_version_id_job_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_change_events")),
        sa.UniqueConstraint(
            "from_version_id",
            "to_version_id",
            "field_name",
            name="uq_job_change_events_from_to_field",
        ),
    )
    op.create_index(
        "ix_job_change_events_job_id_detected_at",
        "job_change_events",
        ["job_id", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_change_events_to_version_id",
        "job_change_events",
        ["to_version_id"],
        unique=False,
    )


def downgrade() -> None:
    """Reverse this revision's schema changes."""
    op.drop_index("ix_job_change_events_to_version_id", table_name="job_change_events")
    op.drop_index(
        "ix_job_change_events_job_id_detected_at", table_name="job_change_events"
    )
    op.drop_table("job_change_events")
    op.drop_index(
        "ix_job_lifecycle_events_pipeline_run_id", table_name="job_lifecycle_events"
    )
    op.drop_index(
        "ix_job_lifecycle_events_job_id_occurred_at", table_name="job_lifecycle_events"
    )
    op.drop_table("job_lifecycle_events")
    op.drop_constraint(
        op.f("ck_jobs_consecutive_absent_runs_non_negative"), "jobs", type_="check"
    )
    op.drop_column("jobs", "absence_first_detected_at")
    op.drop_column("jobs", "consecutive_absent_runs")
