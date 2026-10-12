from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from app.jobs.lifecycle_errors import (
    PresenceDataInvariantError,
    PresenceReconciliationNotAllowedError,
)
from app.jobs.presence import (
    PresenceRecord,
    PresenceRun,
    PresenceUnsafeReason,
    build_presence_set,
)

RUN_ID, SOURCE_ID, SNAPSHOT_ID = uuid4(), uuid4(), uuid4()


def run(valid: int, quarantined: int = 0) -> PresenceRun:
    return PresenceRun(
        RUN_ID,
        SOURCE_ID,
        "completed_with_errors" if quarantined else "completed",
        valid + quarantined,
        valid,
        quarantined,
    )


def record(external_id: str | None, index: int) -> PresenceRecord:
    return PresenceRecord(SOURCE_ID, SNAPSHOT_ID, RUN_ID, f"jobs[{index}]", external_id)


def test_complete_run_is_safe_with_immutable_ids() -> None:
    result = build_presence_set(run(3), [record(str(i), i) for i in range(3)], [])

    assert result.present_external_job_ids == frozenset({"0", "1", "2"})
    assert result.observed_external_job_ids == result.present_external_job_ids
    assert result.recoverable_quarantine_external_job_ids == frozenset()
    assert result.observed_record_count == 3
    assert result.presence_reconciliation_safe is True
    assert result.unsafe_reason is None
    with pytest.raises(FrozenInstanceError):
        result.records_fetched = 99  # type: ignore[misc]


def test_recoverable_partial_run_is_safe_and_retains_evidence_strength() -> None:
    result = build_presence_set(
        run(2, 1), [record("1001", 0), record("1002", 1)], [record("1003", 2)]
    )

    assert result.present_external_job_ids == frozenset({"1001", "1002", "1003"})
    assert result.observed_external_job_ids == frozenset({"1001", "1002"})
    assert result.recoverable_quarantine_external_job_ids == frozenset({"1003"})
    assert result.recoverable_quarantine_count == 1
    assert result.unidentified_quarantine_count == 0
    assert result.presence_reconciliation_safe is True


@pytest.mark.parametrize("unusable_id", [None, "", "   "])
def test_unidentified_quarantine_is_unsafe_but_returns_known_ids(
    unusable_id: str | None,
) -> None:
    result = build_presence_set(
        run(1, 1), [record("1001", 0)], [record(unusable_id, 1)]
    )

    assert result.present_external_job_ids == frozenset({"1001"})
    assert result.presence_reconciliation_safe is False
    assert result.unidentified_quarantine_count == 1
    assert result.recoverable_quarantine_count == 0
    assert result.unsafe_reason is PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS


def test_successful_empty_board_is_safe() -> None:
    result = build_presence_set(run(0), [], [])

    assert result.present_external_job_ids == frozenset()
    assert result.presence_reconciliation_safe is True
    assert result.records_fetched == result.observed_record_count == 0


def test_mapping_failure_retains_presence_without_successful_evidence() -> None:
    failed = record("1001", 0)
    result = build_presence_set(run(1, 1), [failed, record("1002", 1)], [failed])

    assert result.observed_record_count == 2
    assert result.observed_external_job_ids == frozenset({"1002"})
    assert result.recoverable_quarantine_external_job_ids == frozenset({"1001"})
    assert result.present_external_job_ids == frozenset({"1001", "1002"})
    assert result.presence_reconciliation_safe is True


def test_duplicate_id_at_different_locators_does_not_hide_successful_evidence() -> None:
    result = build_presence_set(
        run(1, 2), [record("1001", 0)], [record("1001", 1), record("1001", 2)]
    )

    assert result.present_external_job_ids == frozenset({"1001"})
    assert result.observed_external_job_ids == frozenset({"1001"})
    assert result.recoverable_quarantine_count == 2
    assert result.quarantined_record_count == 2
    assert result.records_fetched == 3


def test_id_case_and_stored_whitespace_are_preserved() -> None:
    result = build_presence_set(run(1, 1), [record("AbC", 0)], [record(" abc ", 1)])

    assert result.present_external_job_ids == frozenset({"AbC", " abc "})


@pytest.mark.parametrize("status", ["pending", "running", "failed", "unknown"])
def test_non_successful_statuses_are_rejected(status: str) -> None:
    with pytest.raises(PresenceReconciliationNotAllowedError):
        build_presence_set(replace(run(0), status=status), [], [])


@pytest.mark.parametrize(
    "invalid_run",
    [
        replace(run(0), records_fetched=-1),
        replace(run(0), records_valid=-1),
        replace(run(0), records_quarantined=-1),
        replace(run(0), records_fetched=1),
    ],
)
def test_inconsistent_metrics_are_invariant_errors(invalid_run: PresenceRun) -> None:
    with pytest.raises(PresenceDataInvariantError):
        build_presence_set(invalid_run, [], [])


def test_missing_observation_is_an_invariant_error() -> None:
    with pytest.raises(PresenceDataInvariantError, match="records_valid"):
        build_presence_set(run(2), [record("1001", 0)], [])


def test_missing_quarantine_is_an_invariant_error() -> None:
    with pytest.raises(PresenceDataInvariantError, match="quarantine count"):
        build_presence_set(run(0, 2), [], [record("1001", 0)])


def test_overlap_with_conflicting_ids_is_an_invariant_error() -> None:
    with pytest.raises(PresenceDataInvariantError, match="disagree on external ID"):
        build_presence_set(run(0, 1), [record("1001", 0)], [record("1002", 0)])


def test_missing_locators_cannot_prove_an_overlap() -> None:
    unidentified_location = replace(record("1001", 0), raw_record_locator=None)
    with pytest.raises(PresenceDataInvariantError, match="records_valid"):
        build_presence_set(run(0, 1), [unidentified_location], [unidentified_location])


@pytest.mark.parametrize("record_type", ["observation", "quarantine"])
@pytest.mark.parametrize("mismatch", ["source", "snapshot_run"])
def test_source_and_snapshot_lineage_mismatches_are_rejected(
    record_type: str,
    mismatch: str,
) -> None:
    invalid = record("1001", 0)
    if mismatch == "source":
        invalid = replace(invalid, source_connection_id=uuid4())
    else:
        invalid = replace(invalid, snapshot_pipeline_run_id=uuid4())
    observations = [invalid] if record_type == "observation" else []
    quarantines = [invalid] if record_type == "quarantine" else []
    with pytest.raises(PresenceDataInvariantError):
        build_presence_set(
            run(len(observations), len(quarantines)), observations, quarantines
        )


@pytest.mark.parametrize("record_type", ["observation", "quarantine"])
def test_duplicate_raw_record_outcomes_are_rejected(record_type: str) -> None:
    records = [record("1001", 0), record("1002", 0)]
    with pytest.raises(
        PresenceDataInvariantError, match="duplicate processing outcomes"
    ):
        build_presence_set(
            run(
                2 if record_type == "observation" else 0,
                2 if record_type == "quarantine" else 0,
            ),
            records if record_type == "observation" else [],
            records if record_type == "quarantine" else [],
        )


def test_duplicate_observation_ids_are_rejected() -> None:
    with pytest.raises(
        PresenceDataInvariantError, match="duplicate observation external IDs"
    ):
        build_presence_set(run(2), [record("1001", 0), record("1001", 1)], [])


@pytest.mark.parametrize("unusable_id", [None, "", " "])
def test_unusable_observation_ids_are_invariant_errors(unusable_id: str | None) -> None:
    with pytest.raises(PresenceDataInvariantError, match="unusable external ID"):
        build_presence_set(run(1), [record(unusable_id, 0)], [])
