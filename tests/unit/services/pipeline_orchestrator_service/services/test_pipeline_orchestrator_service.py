from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import CashflowCalculatedEvent, TransactionEvent

from src.services.pipeline_orchestrator_service.app.services.pipeline_orchestrator_service import (
    PipelineOrchestratorService,
)


@dataclass
class _Stage:
    transaction_id: str
    portfolio_id: str
    security_id: str | None
    business_date: date
    epoch: int
    status: str = "PENDING"
    cost_event_seen: bool = False
    cashflow_event_seen: bool = False


class _RepoStub:
    def __init__(self) -> None:
        self._stage: _Stage | None = None
        self.force_claim_result: bool | None = None

    async def upsert_stage_flags(self, **kwargs):
        if self._stage is None:
            self._stage = _Stage(
                transaction_id=kwargs["transaction_id"],
                portfolio_id=kwargs["portfolio_id"],
                security_id=kwargs["security_id"],
                business_date=kwargs["business_date"],
                epoch=kwargs["epoch"],
                cost_event_seen=kwargs["cost_event_seen"],
                cashflow_event_seen=kwargs["cashflow_event_seen"],
            )
            return self._stage

        self._stage.cost_event_seen = self._stage.cost_event_seen or kwargs["cost_event_seen"]
        self._stage.cashflow_event_seen = (
            self._stage.cashflow_event_seen or kwargs["cashflow_event_seen"]
        )
        return self._stage

    async def mark_stage_completed_if_pending(self, stage):
        if self.force_claim_result is not None:
            return self.force_claim_result
        if stage.status != "PENDING":
            return False
        stage.status = "COMPLETED"
        return True


def _txn_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-PIPE-1",
        portfolio_id="PORT-1",
        instrument_id="INST-1",
        security_id="SEC-1",
        transaction_date=datetime(2026, 3, 7, 10, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        epoch=0,
    )


def _cashflow_event() -> CashflowCalculatedEvent:
    return CashflowCalculatedEvent(
        cashflow_id=1,
        transaction_id="TXN-PIPE-1",
        portfolio_id="PORT-1",
        security_id="SEC-1",
        cashflow_date=date(2026, 3, 7),
        epoch=0,
        amount=Decimal("-1000"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        is_position_flow=True,
        is_portfolio_flow=False,
        calculation_type="TRANSACTION_BASED",
    )


@pytest.mark.asyncio
async def test_only_single_signal_does_not_emit_completion_event():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_processed_transaction(_txn_event(), correlation_id="corr-1")

    outbox_repo.create_outbox_event.assert_not_called()


@pytest.mark.asyncio
async def test_cost_and_cashflow_signals_emit_single_completion_event():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_processed_transaction(_txn_event(), correlation_id="corr-2")
    await service.register_cashflow_calculated(_cashflow_event(), correlation_id="corr-2")

    outbox_repo.create_outbox_event.assert_awaited_once()
    payload = outbox_repo.create_outbox_event.await_args.kwargs["payload"]
    assert payload["transaction_id"] == "TXN-PIPE-1"
    assert payload["stage_name"] == "TRANSACTION_PROCESSING"
    assert payload["readiness_reason"] == "cost_and_cashflow_completed"


@pytest.mark.asyncio
async def test_no_emit_when_stage_claim_lost_to_competing_worker():
    repo = _RepoStub()
    repo.force_claim_result = False
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_processed_transaction(_txn_event(), correlation_id="corr-3")
    await service.register_cashflow_calculated(_cashflow_event(), correlation_id="corr-3")

    outbox_repo.create_outbox_event.assert_not_called()
