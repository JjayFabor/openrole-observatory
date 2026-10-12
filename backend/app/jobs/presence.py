from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.jobs.lifecycle_errors import (
    PresenceDataInvariantError,
    PresenceReconciliationNotAllowedError,
)


class PresenceUnsafeReason(StrEnum):
    UNIDENTIFIED_QUARANTINE_RECORDS = "unidentified_quarantine_records"


@dataclass(frozen=True, slots=True)
class PresenceRun:
    pipeline_run_id: UUID
    source_connection_id: UUID
    status: str
    records_fetched: int
    records_valid: int
    records_quarantined: int


@dataclass(frozen=True, slots=True)
class PresenceRecord:
    source_connection_id: UUID
    raw_snapshot_id: UUID
    snapshot_pipeline_run_id: UUID
    raw_record_locator: str | None
    external_job_id: str | None


@dataclass(frozen=True, slots=True)
class PresenceSetResult:
    pipeline_run_id: UUID
    source_connection_id: UUID
    observed_external_job_ids: frozenset[str]
    recoverable_quarantine_external_job_ids: frozenset[str]
    records_fetched: int
    observed_record_count: int
    quarantined_record_count: int
    recoverable_quarantine_count: int
    unidentified_quarantine_count: int
    presence_reconciliation_safe: bool
    unsafe_reason: PresenceUnsafeReason | None

    @property
    def present_external_job_ids(self) -> frozenset[str]:
        return (
            self.observed_external_job_ids
            | self.recoverable_quarantine_external_job_ids
        )


def build_presence_set(
    run: PresenceRun,
    observations: Sequence[PresenceRecord],
    quarantines: Sequence[PresenceRecord],
) -> PresenceSetResult:
    """Validate durable processing outcomes and distinguish their evidence strength."""
    if run.status not in {"completed", "completed_with_errors"}:
        raise PresenceReconciliationNotAllowedError(run.pipeline_run_id, run.status)
    if min(run.records_fetched, run.records_valid, run.records_quarantined) < 0:
        raise PresenceDataInvariantError(
            run.pipeline_run_id, "record metrics are negative"
        )
    if run.records_fetched != run.records_valid + run.records_quarantined:
        raise PresenceDataInvariantError(
            run.pipeline_run_id, "records_fetched does not equal valid plus quarantined"
        )
    if len(quarantines) != run.records_quarantined:
        raise PresenceDataInvariantError(
            run.pipeline_run_id, "persisted quarantine count does not match run metrics"
        )

    _index_record_locations(run, observations)
    quarantines_by_locator = _index_record_locations(run, quarantines)
    observation_ids: set[str] = set()
    successful_ids: set[str] = set()
    overlapping_count = 0
    for observation in observations:
        external_id = observation.external_job_id
        if not _usable_external_id(external_id):
            raise PresenceDataInvariantError(
                run.pipeline_run_id, "an observation has an unusable external ID"
            )
        assert external_id is not None
        if external_id in observation_ids:
            raise PresenceDataInvariantError(
                run.pipeline_run_id, "duplicate observation external IDs"
            )
        observation_ids.add(external_id)
        location = _record_location(observation)
        quarantine = (
            quarantines_by_locator.get(location) if location is not None else None
        )
        if quarantine is None:
            successful_ids.add(external_id)
        else:
            if quarantine.external_job_id != external_id:
                raise PresenceDataInvariantError(
                    run.pipeline_run_id, "overlapping outcomes disagree on external ID"
                )
            overlapping_count += 1

    # Phase 1 retains observations even when later canonical processing quarantines them.
    if len(observations) - overlapping_count != run.records_valid:
        raise PresenceDataInvariantError(
            run.pipeline_run_id,
            "observation count minus quarantined overlaps does not match records_valid",
        )

    recoverable_ids: set[str] = set()
    recoverable_count = 0
    for quarantine in quarantines:
        external_id = quarantine.external_job_id
        if _usable_external_id(external_id):
            assert external_id is not None
            recoverable_ids.add(external_id)
            recoverable_count += 1
    unidentified_count = len(quarantines) - recoverable_count
    safe = unidentified_count == 0

    return PresenceSetResult(
        pipeline_run_id=run.pipeline_run_id,
        source_connection_id=run.source_connection_id,
        observed_external_job_ids=frozenset(successful_ids),
        recoverable_quarantine_external_job_ids=frozenset(recoverable_ids),
        records_fetched=run.records_fetched,
        observed_record_count=len(observations),
        quarantined_record_count=len(quarantines),
        recoverable_quarantine_count=recoverable_count,
        unidentified_quarantine_count=unidentified_count,
        presence_reconciliation_safe=safe,
        unsafe_reason=(
            None if safe else PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS
        ),
    )


def _usable_external_id(external_id: str | None) -> bool:
    return external_id is not None and bool(external_id.strip())


def _record_location(record: PresenceRecord) -> tuple[UUID, str] | None:
    if record.raw_record_locator is None:
        return None
    return record.raw_snapshot_id, record.raw_record_locator


def _index_record_locations(
    run: PresenceRun, records: Sequence[PresenceRecord]
) -> dict[tuple[UUID, str], PresenceRecord]:
    by_location: dict[tuple[UUID, str], PresenceRecord] = {}
    for record in records:
        if record.source_connection_id != run.source_connection_id:
            raise PresenceDataInvariantError(
                run.pipeline_run_id, "processing record belongs to another source"
            )
        if record.snapshot_pipeline_run_id != run.pipeline_run_id:
            raise PresenceDataInvariantError(
                run.pipeline_run_id,
                "processing record references another run's snapshot",
            )
        location = _record_location(record)
        if location is not None:
            if location in by_location:
                raise PresenceDataInvariantError(
                    run.pipeline_run_id,
                    "duplicate processing outcomes at one raw locator",
                )
            by_location[location] = record
    return by_location
