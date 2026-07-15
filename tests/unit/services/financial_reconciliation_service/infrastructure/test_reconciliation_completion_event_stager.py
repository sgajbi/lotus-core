"""Tests for transactional reconciliation completion event staging."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import (
    FinancialReconciliationCompletedEvent,
    PortfolioDayControlsEvaluatedEvent,
)

from src.services.financial_reconciliation_service.app.domain.reconciliation_control import (
    FinancialReconciliationCompletion,
)
from src.services.financial_reconciliation_service.app.infrastructure import (
    reconciliation_completion_event_stager as event_stager,
)

pytestmark = pytest.mark.asyncio


def _completion() -> FinancialReconciliationCompletion:
    return FinancialReconciliationCompletion(
        portfolio_id="PORT-CTRL-1",
        business_date=date(2026, 3, 8),
        epoch=3,
        outcome_status="REQUIRES_REPLAY",
        reconciliation_types=("transaction_cashflow",),
        blocking_reconciliation_types=("transaction_cashflow",),
        run_ids={"transaction_cashflow": "run-1"},
        error_count=1,
        warning_count=2,
        requested_by="system_pipeline",
        trigger_stage="portfolio_day.aggregation.completed",
    )


async def test_stages_existing_completion_contract_without_payload_drift() -> None:
    outbox_repository = AsyncMock()
    stager = event_stager.TransactionalReconciliationCompletionEventStager(
        outbox_repository
    )

    await stager.stage_reconciliation_completed(_completion(), correlation_id="corr-1")

    call = outbox_repository.create_outbox_event.await_args
    assert call.kwargs["aggregate_type"] == "FinancialReconciliation"
    assert call.kwargs["aggregate_id"] == "PORT-CTRL-1:2026-03-08:3"
    assert call.kwargs["event_type"] == "FinancialReconciliationCompleted"
    assert call.kwargs["topic"] == "portfolio_day.reconciliation.completed"
    payload = FinancialReconciliationCompletedEvent.model_validate(call.kwargs["payload"])
    assert payload.outcome_status == "REQUIRES_REPLAY"
    assert payload.blocking_reconciliation_types == ["transaction_cashflow"]


async def test_stages_existing_controls_contract_with_recorded_status() -> None:
    outbox_repository = AsyncMock()
    stager = event_stager.TransactionalReconciliationCompletionEventStager(
        outbox_repository
    )

    await stager.stage_controls_evaluated(
        _completion(),
        status="FAILED",
        controls_blocking=True,
        correlation_id="corr-2",
    )

    call = outbox_repository.create_outbox_event.await_args
    assert call.kwargs["aggregate_type"] == "PipelineStage"
    assert call.kwargs["aggregate_id"] == "PORT-CTRL-1:2026-03-08:3"
    assert call.kwargs["event_type"] == "PortfolioDayControlsEvaluated"
    assert call.kwargs["topic"] == "portfolio_day.controls.evaluated"
    payload = PortfolioDayControlsEvaluatedEvent.model_validate(call.kwargs["payload"])
    assert payload.status == "FAILED"
    assert payload.controls_blocking is True
    assert payload.publish_allowed is False
    assert payload.blocking_reconciliation_types == ["transaction_cashflow"]
