"""Tests for direct financial reconciliation completion ownership."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.services.financial_reconciliation_service.app.application import (
    record_reconciliation_completion,
)
from src.services.financial_reconciliation_service.app.domain.reconciliation_control import (
    FinancialReconciliationCompletion,
    RecordedReconciliationControl,
)

pytestmark = pytest.mark.asyncio


def _completion(*, epoch: int = 3, status: str = "COMPLETED") -> FinancialReconciliationCompletion:
    return FinancialReconciliationCompletion(
        portfolio_id="PORT-CTRL-1",
        business_date=date(2026, 3, 8),
        epoch=epoch,
        outcome_status=status,
        reconciliation_types=("transaction_cashflow", "position_valuation"),
        blocking_reconciliation_types=("transaction_cashflow",) if status != "COMPLETED" else (),
        run_ids={"transaction_cashflow": "run-1", "position_valuation": "run-2"},
        error_count=1 if status != "COMPLETED" else 0,
        warning_count=1,
        requested_by="system_pipeline",
        trigger_stage="portfolio_day.aggregation.completed",
    )


async def test_latest_completion_records_evidence_and_stages_both_contracts() -> None:
    evidence_repository = AsyncMock()
    event_stager = AsyncMock()
    evidence_repository.record_completion.return_value = RecordedReconciliationControl(
        status="REQUIRES_REPLAY",
        latest_epoch=3,
    )
    use_case = record_reconciliation_completion.RecordFinancialReconciliationCompletion(
        evidence_repository=evidence_repository,
        event_stager=event_stager,
    )
    completion = _completion(status="REQUIRES_REPLAY")

    await use_case.execute(completion, correlation_id="corr-1")

    evidence_repository.record_completion.assert_awaited_once_with(completion)
    event_stager.stage_reconciliation_completed.assert_awaited_once_with(
        completion,
        correlation_id="corr-1",
    )
    event_stager.stage_controls_evaluated.assert_awaited_once_with(
        completion,
        status="REQUIRES_REPLAY",
        controls_blocking=True,
        correlation_id="corr-1",
    )


async def test_stale_completion_preserves_completion_contract_without_controls_event() -> None:
    evidence_repository = AsyncMock()
    event_stager = AsyncMock()
    evidence_repository.record_completion.return_value = RecordedReconciliationControl(
        status="REQUIRES_REPLAY",
        latest_epoch=4,
    )
    use_case = record_reconciliation_completion.RecordFinancialReconciliationCompletion(
        evidence_repository=evidence_repository,
        event_stager=event_stager,
    )
    completion = _completion(epoch=3, status="REQUIRES_REPLAY")

    await use_case.execute(completion, correlation_id="corr-stale")

    event_stager.stage_reconciliation_completed.assert_awaited_once()
    event_stager.stage_controls_evaluated.assert_not_awaited()
