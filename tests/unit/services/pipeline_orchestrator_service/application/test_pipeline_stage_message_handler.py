from __future__ import annotations

from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest
from portfolio_common.events import (
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
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
async def test_handler_skips_registration_for_duplicate_event_claim() -> None:
    unit_of_work = FakePipelineStageUnitOfWork(claim_result=False)
    handler = handler_module.PipelineStageMessageHandler(unit_of_work_factory=lambda: unit_of_work)

    result = await handler.handle_portfolio_aggregation_completed(
        event_id="portfolio_day.aggregation.completed-0-8",
        event=_aggregation_event(),
        correlation_id="corr-agg",
    )

    assert result.processed is False
    assert result.duplicate is True
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
        await handler.handle_portfolio_aggregation_completed(
            event_id="portfolio_day.aggregation.completed-0-8",
            event=_aggregation_event(),
            correlation_id="corr-stage",
        )


def test_pipeline_stage_consumers_do_not_assemble_repositories_or_services() -> None:
    consumer_paths = [
        Path(
            "src/services/pipeline_orchestrator_service/app/consumers/"
            "financial_reconciliation_completion_consumer.py"
        ),
        Path(
            "src/services/pipeline_orchestrator_service/app/consumers/"
            "portfolio_aggregation_stage_consumer.py"
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
