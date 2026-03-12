from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import (
    CashflowCalculatedEvent,
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
    TransactionEvent,
)

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
        self.control_stage = None
        self.latest_control_epoch: int | None = None

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

    async def upsert_portfolio_control_stage_status(self, **kwargs):
        self.latest_control_epoch = max(
            self.latest_control_epoch or kwargs["epoch"], kwargs["epoch"]
        )
        if self.control_stage is None:
            self.control_stage = _Stage(
                transaction_id=f"portfolio-stage:{kwargs['stage_name']}:{kwargs['portfolio_id']}",
                portfolio_id=kwargs["portfolio_id"],
                security_id=None,
                business_date=kwargs["business_date"],
                epoch=kwargs["epoch"],
                status=kwargs["status"],
            )
        else:
            rank = {"PENDING": 0, "COMPLETED": 1, "REQUIRES_REPLAY": 2, "FAILED": 3}
            existing = rank.get(self.control_stage.status, 0)
            incoming = rank.get(kwargs["status"], 0)
            if incoming > existing:
                self.control_stage.status = kwargs["status"]
            self.control_stage.business_date = kwargs["business_date"]
            self.control_stage.epoch = kwargs["epoch"]
        return self.control_stage

    async def get_latest_portfolio_control_stage_epoch(self, **kwargs):
        return self.latest_control_epoch


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

    assert outbox_repo.create_outbox_event.await_count == 2
    calls = outbox_repo.create_outbox_event.await_args_list
    completion_payload = calls[0].kwargs["payload"]
    readiness_payload = calls[1].kwargs["payload"]
    assert completion_payload["transaction_id"] == "TXN-PIPE-1"
    assert completion_payload["stage_name"] == "TRANSACTION_PROCESSING"
    assert completion_payload["readiness_reason"] == "cost_and_cashflow_completed"
    assert readiness_payload["portfolio_id"] == "PORT-1"
    assert readiness_payload["security_id"] == "SEC-1"


@pytest.mark.asyncio
async def test_no_emit_when_stage_claim_lost_to_competing_worker():
    repo = _RepoStub()
    repo.force_claim_result = False
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_processed_transaction(_txn_event(), correlation_id="corr-3")
    await service.register_cashflow_calculated(_cashflow_event(), correlation_id="corr-3")

    outbox_repo.create_outbox_event.assert_not_called()


@pytest.mark.asyncio
async def test_portfolio_aggregation_completion_emits_reconciliation_request():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_portfolio_aggregation_completed(
        PortfolioAggregationDayCompletedEvent(
            portfolio_id="PORT-1",
            aggregation_date=date(2026, 3, 7),
            epoch=2,
            correlation_id="corr-4",
        ),
        correlation_id="corr-4",
    )

    outbox_repo.create_outbox_event.assert_awaited_once()
    call = outbox_repo.create_outbox_event.await_args
    assert call.kwargs["event_type"] == "FinancialReconciliationRequested"
    assert call.kwargs["aggregate_id"] == "PORT-1:2026-03-07:2"
    assert call.kwargs["payload"]["reconciliation_types"] == [
        "transaction_cashflow",
        "position_valuation",
        "timeseries_integrity",
    ]


@pytest.mark.asyncio
async def test_reconciliation_completion_updates_control_stage_and_emits_controls_event():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_financial_reconciliation_completed(
        FinancialReconciliationCompletedEvent(
            portfolio_id="PORT-1",
            business_date=date(2026, 3, 7),
            epoch=2,
            outcome_status="REQUIRES_REPLAY",
            reconciliation_types=[
                "transaction_cashflow",
                "position_valuation",
                "timeseries_integrity",
            ],
            blocking_reconciliation_types=["transaction_cashflow"],
            run_ids={
                "transaction_cashflow": "recon-tx",
                "position_valuation": "recon-val",
                "timeseries_integrity": "recon-ts",
            },
            error_count=2,
            warning_count=1,
            correlation_id="corr-5",
        ),
        correlation_id="corr-5",
    )

    assert repo.control_stage is not None
    assert repo.control_stage.status == "REQUIRES_REPLAY"
    outbox_repo.create_outbox_event.assert_awaited_once()
    call = outbox_repo.create_outbox_event.await_args
    assert call.kwargs["event_type"] == "PortfolioDayControlsEvaluated"
    assert call.kwargs["topic"] == "portfolio_day_controls_evaluated"
    assert call.kwargs["payload"]["status"] == "REQUIRES_REPLAY"
    assert call.kwargs["payload"]["controls_blocking"] is True
    assert call.kwargs["payload"]["publish_allowed"] is False
    assert call.kwargs["payload"]["blocking_reconciliation_types"] == ["transaction_cashflow"]


@pytest.mark.asyncio
async def test_completed_reconciliation_emits_publish_allowed_controls_event():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_financial_reconciliation_completed(
        FinancialReconciliationCompletedEvent(
            portfolio_id="PORT-1",
            business_date=date(2026, 3, 7),
            epoch=2,
            outcome_status="COMPLETED",
            reconciliation_types=["transaction_cashflow"],
            blocking_reconciliation_types=[],
            run_ids={"transaction_cashflow": "recon-tx"},
            error_count=0,
            warning_count=1,
            correlation_id="corr-6",
        ),
        correlation_id="corr-6",
    )

    call = outbox_repo.create_outbox_event.await_args
    assert call.kwargs["payload"]["status"] == "COMPLETED"
    assert call.kwargs["payload"]["controls_blocking"] is False
    assert call.kwargs["payload"]["publish_allowed"] is True


@pytest.mark.asyncio
async def test_stale_completed_reconciliation_does_not_downgrade_blocking_stage():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_financial_reconciliation_completed(
        FinancialReconciliationCompletedEvent(
            portfolio_id="PORT-1",
            business_date=date(2026, 3, 7),
            epoch=2,
            outcome_status="REQUIRES_REPLAY",
            reconciliation_types=["transaction_cashflow"],
            blocking_reconciliation_types=["transaction_cashflow"],
            run_ids={"transaction_cashflow": "recon-blocking"},
            error_count=1,
            warning_count=0,
            correlation_id="corr-7",
        ),
        correlation_id="corr-7",
    )
    outbox_repo.create_outbox_event.reset_mock()

    await service.register_financial_reconciliation_completed(
        FinancialReconciliationCompletedEvent(
            portfolio_id="PORT-1",
            business_date=date(2026, 3, 7),
            epoch=2,
            outcome_status="COMPLETED",
            reconciliation_types=["transaction_cashflow"],
            blocking_reconciliation_types=[],
            run_ids={"transaction_cashflow": "recon-stale"},
            error_count=0,
            warning_count=0,
            correlation_id="corr-8",
        ),
        correlation_id="corr-8",
    )

    assert repo.control_stage is not None
    assert repo.control_stage.status == "REQUIRES_REPLAY"
    call = outbox_repo.create_outbox_event.await_args
    assert call.kwargs["payload"]["status"] == "REQUIRES_REPLAY"
    assert call.kwargs["payload"]["controls_blocking"] is True
    assert call.kwargs["payload"]["publish_allowed"] is False


@pytest.mark.asyncio
async def test_older_epoch_reconciliation_completion_does_not_emit_controls_event():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_financial_reconciliation_completed(
        FinancialReconciliationCompletedEvent(
            portfolio_id="PORT-1",
            business_date=date(2026, 3, 7),
            epoch=3,
            outcome_status="COMPLETED",
            reconciliation_types=["transaction_cashflow"],
            blocking_reconciliation_types=[],
            run_ids={"transaction_cashflow": "recon-latest"},
            error_count=0,
            warning_count=0,
            correlation_id="corr-9",
        ),
        correlation_id="corr-9",
    )
    outbox_repo.create_outbox_event.reset_mock()

    await service.register_financial_reconciliation_completed(
        FinancialReconciliationCompletedEvent(
            portfolio_id="PORT-1",
            business_date=date(2026, 3, 7),
            epoch=2,
            outcome_status="REQUIRES_REPLAY",
            reconciliation_types=["transaction_cashflow"],
            blocking_reconciliation_types=["transaction_cashflow"],
            run_ids={"transaction_cashflow": "recon-stale"},
            error_count=1,
            warning_count=0,
            correlation_id="corr-10",
        ),
        correlation_id="corr-10",
    )

    outbox_repo.create_outbox_event.assert_not_called()
