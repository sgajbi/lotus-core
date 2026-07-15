from dataclasses import dataclass
from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import (
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
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
        self.control_stage = None
        self.latest_control_epoch: int | None = None

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

    await service.register_reconciliation_completed(
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
    assert call.kwargs["topic"] == "portfolio_day.controls.evaluated"
    assert call.kwargs["payload"]["status"] == "REQUIRES_REPLAY"
    assert call.kwargs["payload"]["controls_blocking"] is True
    assert call.kwargs["payload"]["publish_allowed"] is False
    assert call.kwargs["payload"]["blocking_reconciliation_types"] == ["transaction_cashflow"]


@pytest.mark.asyncio
async def test_completed_reconciliation_emits_publish_allowed_controls_event():
    repo = _RepoStub()
    outbox_repo = AsyncMock()
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)

    await service.register_reconciliation_completed(
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

    await service.register_reconciliation_completed(
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

    await service.register_reconciliation_completed(
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

    await service.register_reconciliation_completed(
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

    await service.register_reconciliation_completed(
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
