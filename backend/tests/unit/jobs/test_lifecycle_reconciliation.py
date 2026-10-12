from dataclasses import replace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.absence_confirmation import AbsenceConfirmationResult
from app.jobs.first_absence import FirstAbsenceDetectionResult
from app.jobs.lifecycle_reconciliation import LifecycleReconciliationService
from app.jobs.presence import PresenceRun, PresenceUnsafeReason, build_presence_set
from app.jobs.present_reconciliation import PresentJobReconciliationResult


@pytest.mark.asyncio
@pytest.mark.parametrize("safe", [True, False])
async def test_safe_presence_controls_lifecycle_call_order(
    monkeypatch: pytest.MonkeyPatch, safe: bool
) -> None:
    receipt = PresenceRun(uuid4(), uuid4(), "completed", 0, 0, 0)
    presence = build_presence_set(receipt, [], [])
    if not safe:
        presence = replace(
            presence,
            presence_reconciliation_safe=False,
            unsafe_reason=PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS,
        )
    builder = MagicMock()
    builder.build_presence_set = AsyncMock(return_value=presence)
    monkeypatch.setattr(
        "app.jobs.lifecycle_reconciliation.PresenceSetBuilder",
        MagicMock(return_value=builder),
    )
    calls: list[str] = []

    async def present(
        *args: object, **kwargs: object
    ) -> PresentJobReconciliationResult:
        calls.append("present")
        assert kwargs["processed_run"] == receipt
        assert kwargs["session"] is shared_session
        return PresentJobReconciliationResult(
            receipt.pipeline_run_id, receipt.source_connection_id, 5, 1, 2, 0
        )

    async def confirm(*args: object, **kwargs: object) -> AbsenceConfirmationResult:
        calls.append("confirm")
        return AbsenceConfirmationResult(
            receipt.pipeline_run_id, receipt.source_connection_id, 3, 3, 0, 0
        )

    async def first(*args: object, **kwargs: object) -> FirstAbsenceDetectionResult:
        calls.append("first")
        return FirstAbsenceDetectionResult(
            receipt.pipeline_run_id, receipt.source_connection_id, 5, 4, 0
        )

    present_service, confirm_service, first_service = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    present_service.reconcile_present_jobs = AsyncMock(side_effect=present)
    confirm_service.confirm_absences = AsyncMock(side_effect=confirm)
    first_service.detect_first_absences = AsyncMock(side_effect=first)
    factory = cast(async_sessionmaker[AsyncSession], MagicMock())
    coordinator = LifecycleReconciliationService(
        factory,
        present_reconciliation=present_service,
        absence_confirmation=confirm_service,
        first_absence_detection=first_service,
    )

    shared_session = cast(AsyncSession, MagicMock())
    result = await coordinator.reconcile_processed_run(receipt, session=shared_session)
    cast(MagicMock, factory).assert_not_called()

    assert result.performed is safe
    if safe:
        assert calls == ["present", "confirm", "first"]
        assert result.tentative_absences_reset == 1
        assert result.jobs_reappeared == 2
        assert result.jobs_confirmed_not_observed == 3
        assert result.first_absences_detected == 4
    else:
        assert calls == []
        assert (
            result.skipped_reason
            is PresenceUnsafeReason.UNIDENTIFIED_QUARANTINE_RECORDS
        )
        present_service.reconcile_present_jobs.assert_not_awaited()
        confirm_service.confirm_absences.assert_not_awaited()
        first_service.detect_first_absences.assert_not_awaited()
