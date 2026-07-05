from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest
from portfolio_common.events import (
    CashflowCalculatedEvent,
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
    TransactionEvent,
)
from sqlalchemy.exc import IntegrityError

from src.services.pipeline_orchestrator_service.app.application import (
    pipeline_stage_message_handler as handler_module,
)


class FakePipelineStageUnitOfWork:
    def __init__(self, *, claim_result: bool = True, enter_error: Exception | None = None) -> None:
        self.claim_result = claim_result
        self.enter_error = enter_error
        self.claims: list[tuple[str, str, str, str | None]] = []
        self.registrations: list[tuple[str, object, str | None]] = []

    async def __aenter__(self) -> Self:
        if self.enter_error is not None:
            raise self.enter_error
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def claim_event_processing(
        self,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: str | None,
    ) -> bool:
        self.claims.append((event_id, portfolio_id, service_name, correlation_id))
        return self.claim_result

    async def register_processed_transaction(
        self,
        event: TransactionEvent,
        correlation_id: str | None,
    ) -> None:
        self.registrations.append(("processed_transaction", event, correlation_id))

    async def register_cashflow_calculated(
        self,
        event: CashflowCalculatedEvent,
        correlation_id: str | None,
    ) -> None:
        self.registrations.append(("cashflow_calculated", event, correlation_id))

    async def register_portfolio_aggregation_completed(
        self,
        event: PortfolioAggregationDayCompletedEvent,
        correlation_id: str | None,
    ) -> None:
        self.registrations.append(("portfolio_aggregation_completed", event, correlation_id))

    async def register_reconciliation_completed(
        self,
        event: FinancialReconciliationCompletedEvent,
        correlation_id: str | None,
    ) -> None:
        self.registrations.append(("reconciliation_completed", event, correlation_id))


def _transaction_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-PIPE-HANDLER-1",
        portfolio_id="PORT-PIPE-1",
        instrument_id="INST-PIPE-1",
        security_id="SEC-PIPE-1",
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
        cashflow_id=1001,
        portfolio_id="PORT-PIPE-1",
        transaction_id="TXN-PIPE-HANDLER-1",
        security_id="SEC-PIPE-1",
        cashflow_date=date(2026, 3, 8),
        amount=Decimal("12.34"),
        currency="USD",
        classification="INCOME",
        timing="SETTLED",
        is_position_flow=True,
        is_portfolio_flow=True,
        calculation_type="DIVIDEND",
        epoch=0,
    )


def _aggregation_event() -> PortfolioAggregationDayCompletedEvent:
    return PortfolioAggregationDayCompletedEvent(
        portfolio_id="PORT-PIPE-1",
        aggregation_date=date(2026, 3, 8),
        epoch=3,
    )


def _reconciliation_event() -> FinancialReconciliationCompletedEvent:
    return FinancialReconciliationCompletedEvent(
        portfolio_id="PORT-PIPE-1",
        business_date=date(2026, 3, 8),
        epoch=3,
        outcome_status="PASSED",
        reconciliation_types=["transaction_cashflow"],
        blocking_reconciliation_types=[],
        run_ids={"transaction_cashflow": "recon-run-1"},
        error_count=0,
        warning_count=0,
        correlation_id="corr-recon",
    )


@pytest.mark.asyncio
async def test_handler_claims_and_registers_processed_transaction_stage() -> None:
    unit_of_work = FakePipelineStageUnitOfWork()
    handler = handler_module.PipelineStageMessageHandler(unit_of_work_factory=lambda: unit_of_work)
    event = _transaction_event()

    result = await handler.handle_processed_transaction(
        event_id="transactions.processed-1-5",
        event=event,
        correlation_id="corr-stage",
    )

    assert result.processed is True
    assert result.duplicate is False
    assert unit_of_work.claims == [
        (
            "transactions.processed-1-5",
            "PORT-PIPE-1",
            "pipeline-orchestrator-processed-txn",
            "corr-stage",
        )
    ]
    assert unit_of_work.registrations == [("processed_transaction", event, "corr-stage")]


@pytest.mark.asyncio
async def test_handler_skips_registration_for_duplicate_event_claim() -> None:
    unit_of_work = FakePipelineStageUnitOfWork(claim_result=False)
    handler = handler_module.PipelineStageMessageHandler(unit_of_work_factory=lambda: unit_of_work)

    result = await handler.handle_cashflow_calculated(
        event_id="cashflows.calculated-0-7",
        event=_cashflow_event(),
        correlation_id="corr-stage",
    )

    assert result.processed is False
    assert result.duplicate is True
    assert unit_of_work.claims == [
        (
            "cashflows.calculated-0-7",
            "PORT-PIPE-1",
            "pipeline-orchestrator-cashflow",
            "corr-stage",
        )
    ]
    assert unit_of_work.registrations == []


@pytest.mark.asyncio
async def test_handler_uses_shared_stage_service_names_for_all_stage_families() -> None:
    unit_of_work = FakePipelineStageUnitOfWork()
    handler = handler_module.PipelineStageMessageHandler(unit_of_work_factory=lambda: unit_of_work)

    await handler.handle_portfolio_aggregation_completed(
        event_id="portfolio_day.aggregation.completed-0-8",
        event=_aggregation_event(),
        correlation_id="corr-agg",
    )
    await handler.handle_reconciliation_completed(
        event_id="portfolio_day.reconciliation.completed-0-9",
        event=_reconciliation_event(),
        correlation_id="corr-recon",
    )

    assert unit_of_work.claims == [
        (
            "portfolio_day.aggregation.completed-0-8",
            "PORT-PIPE-1",
            "pipeline-orchestrator-portfolio-aggregation",
            "corr-agg",
        ),
        (
            "portfolio_day.reconciliation.completed-0-9",
            "PORT-PIPE-1",
            "pipeline-orchestrator-reconciliation-completion",
            "corr-recon",
        ),
    ]
    assert unit_of_work.registrations == [
        ("portfolio_aggregation_completed", _aggregation_event(), "corr-agg"),
        ("reconciliation_completed", _reconciliation_event(), "corr-recon"),
    ]


@pytest.mark.asyncio
async def test_handler_propagates_db_errors_for_consumer_retry_policy() -> None:
    db_error = IntegrityError("claim", {}, RuntimeError("deadlock"))
    handler = handler_module.PipelineStageMessageHandler(
        unit_of_work_factory=lambda: FakePipelineStageUnitOfWork(enter_error=db_error)
    )

    with pytest.raises(IntegrityError):
        await handler.handle_processed_transaction(
            event_id="transactions.processed-1-5",
            event=_transaction_event(),
            correlation_id="corr-stage",
        )


def test_pipeline_stage_consumers_do_not_assemble_repositories_or_services() -> None:
    consumer_paths = [
        Path("src/services/pipeline_orchestrator_service/app/consumers/cashflow_stage_consumer.py"),
        Path(
            "src/services/pipeline_orchestrator_service/app/consumers/"
            "financial_reconciliation_completion_consumer.py"
        ),
        Path(
            "src/services/pipeline_orchestrator_service/app/consumers/"
            "portfolio_aggregation_stage_consumer.py"
        ),
        Path(
            "src/services/pipeline_orchestrator_service/app/consumers/"
            "processed_transaction_stage_consumer.py"
        ),
    ]
    forbidden_snippets = [
        "get_async_db_session",
        "IdempotencyRepository",
        "PipelineStageRepository",
        "OutboxRepository",
        "PipelineOrchestratorService",
    ]

    for consumer_path in consumer_paths:
        source = consumer_path.read_text(encoding="utf-8")
        for forbidden_snippet in forbidden_snippets:
            assert forbidden_snippet not in source, (
                f"{consumer_path} must delegate dependency assembly to the "
                "pipeline stage message handler boundary"
            )
