"""Infrastructure tests for aggregation completion outbox staging."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.outbox_repository import OutboxRepository

from src.services.portfolio_aggregation_service.app.domain.aggregation_records import (
    PortfolioAggregationCompletion,
)
from src.services.portfolio_aggregation_service.app.infrastructure import (
    aggregation_completion_event_stager,
)

pytestmark = pytest.mark.asyncio


async def test_stager_preserves_existing_completion_and_reconciliation_contracts() -> None:
    outbox_repository = AsyncMock(spec=OutboxRepository)
    stager = aggregation_completion_event_stager.TransactionalAggregationCompletionEventStager(
        outbox_repository
    )

    await stager.stage_completion(
        PortfolioAggregationCompletion(
            portfolio_id="PORT-1",
            aggregation_date=date(2026, 7, 15),
            epoch=4,
        ),
        correlation_id="corr-1",
    )

    assert outbox_repository.create_outbox_event.await_count == 2
    completion_call, reconciliation_call = outbox_repository.create_outbox_event.await_args_list
    assert completion_call.kwargs == {
        "aggregate_type": "PortfolioAggregationStage",
        "aggregate_id": "PORT-1:2026-07-15:4",
        "event_type": "PortfolioAggregationDayCompleted",
        "topic": "portfolio_day.aggregation.completed",
        "payload": completion_call.kwargs["payload"],
        "correlation_id": "corr-1",
    }
    assert completion_call.kwargs["payload"]["portfolio_id"] == "PORT-1"
    assert completion_call.kwargs["payload"]["aggregation_date"] == "2026-07-15"
    assert reconciliation_call.kwargs == {
        "aggregate_type": "FinancialReconciliation",
        "aggregate_id": "PORT-1:2026-07-15:4",
        "event_type": "FinancialReconciliationRequested",
        "topic": "portfolio_day.reconciliation.requested",
        "payload": reconciliation_call.kwargs["payload"],
        "correlation_id": "corr-1",
    }
    assert reconciliation_call.kwargs["payload"]["portfolio_id"] == "PORT-1"
    assert reconciliation_call.kwargs["payload"]["business_date"] == "2026-07-15"
    assert reconciliation_call.kwargs["payload"]["epoch"] == 4
    assert reconciliation_call.kwargs["payload"]["correlation_id"] == "corr-1"
