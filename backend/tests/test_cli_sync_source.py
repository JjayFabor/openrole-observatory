from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.cli.sync_source import format_failure, format_success
from app.ingestion.sync import SourceSyncResult
from app.jobs.lifecycle_reconciliation import LifecycleReconciliationResult
from app.jobs.presence import PresenceUnsafeReason
from app.pipeline_runs.models import PipelineRunStatus


def test_cli_success_format_includes_final_metrics() -> None:
    source_id = uuid4()
    run_id = uuid4()
    result = SourceSyncResult(
        pipeline_run_id=run_id,
        source_connection_id=source_id,
        status=PipelineRunStatus.COMPLETED_WITH_ERRORS,
        records_fetched=5,
        records_valid=4,
        records_quarantined=1,
        jobs_new=2,
        jobs_changed=1,
        jobs_unchanged=1,
        started_at=datetime(2026, 10, 10, 9, tzinfo=UTC),
        completed_at=datetime(2026, 10, 10, 10, tzinfo=UTC),
    )

    output = format_success(result)

    assert str(source_id) in output
    assert str(run_id) in output
    assert "Status:      completed_with_errors" in output
    assert "Fetched:     5" in output
    assert "Quarantined: 1" in output
    assert "Changed:     1" in output


def test_cli_failure_format_is_safe_and_includes_run_when_available() -> None:
    run_id = uuid4()

    output = format_failure(code="SOURCE_REQUEST_FAILED", pipeline_run_id=run_id)

    assert (
        output == f"Source sync failed\n\nRun:  {run_id}\nCode: SOURCE_REQUEST_FAILED"
    )


@pytest.mark.parametrize("performed", [True, False])
def test_cli_lifecycle_summary_reports_counts_or_skip(performed: bool) -> None:
    result = SourceSyncResult(
        pipeline_run_id=uuid4(),
        source_connection_id=uuid4(),
        status=PipelineRunStatus.COMPLETED_WITH_ERRORS,
        records_fetched=5,
        records_valid=4,
        records_quarantined=1,
        jobs_new=2,
        jobs_changed=1,
        jobs_unchanged=1,
        started_at=datetime(2026, 10, 10, 9, tzinfo=UTC),
        completed_at=datetime(2026, 10, 10, 10, tzinfo=UTC),
        lifecycle=LifecycleReconciliationResult(
            performed=performed,
            skipped_reason=None
            if performed
            else PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS,
            first_absences_detected=2 if performed else 0,
            jobs_confirmed_not_observed=1 if performed else 0,
            jobs_reappeared=3 if performed else 0,
            tentative_absences_reset=4 if performed else 0,
        ),
    )
    output = format_success(result)
    assert "Lifecycle:" in output
    if performed:
        assert "First absences:    2" in output
        assert "Confirmed absent:  1" in output
        assert "Reappeared:        3" in output
        assert "Absences reset:    4" in output
    else:
        assert "Skipped — source membership incomplete" in output
