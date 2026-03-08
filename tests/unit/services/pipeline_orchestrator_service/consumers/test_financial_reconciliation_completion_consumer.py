import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import FinancialReconciliationCompletedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.pipeline_orchestrator_service.app.consumers import (
    financial_reconciliation_completion_consumer as consumer_module,
)

pytestmark = pytest.mark.asyncio


class _SingleSessionAsyncIterable:
    def __init__(self, session):
        self._session = session
        self._yielded = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return self._session


@pytest.fixture
def consumer() -> consumer_module.FinancialReconciliationCompletionConsumer:
    c = consumer_module.FinancialReconciliationCompletionConsumer(
        bootstrap_servers="mock_server",
        topic="financial_reconciliation_completed",
        group_id="test_group",
    )
    c._send_to_dlq_async = AsyncMock()
    return c


@pytest.fixture
def mock_event() -> FinancialReconciliationCompletedEvent:
    return FinancialReconciliationCompletedEvent(
        portfolio_id="PORT-CTRL-1",
        business_date=date(2026, 3, 8),
        epoch=2,
        outcome_status="REQUIRES_REPLAY",
        reconciliation_types=[
            "transaction_cashflow",
            "position_valuation",
            "timeseries_integrity",
        ],
        blocking_reconciliation_types=["transaction_cashflow"],
        run_ids={"transaction_cashflow": "recon-tx"},
        error_count=1,
        warning_count=0,
        correlation_id="corr-ctrl",
    )


@pytest.fixture
def mock_kafka_message(mock_event: FinancialReconciliationCompletedEvent) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    msg.key.return_value = b"PORT-CTRL-1"
    msg.topic.return_value = "financial_reconciliation_completed"
    msg.partition.return_value = 0
    msg.offset.return_value = 9
    msg.headers.return_value = []
    return msg


@pytest.fixture
def mock_dependencies():
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_service = AsyncMock()
    mock_db_session = AsyncMock(spec=AsyncSession)

    with (
        patch(
            "src.services.pipeline_orchestrator_service.app.consumers.financial_reconciliation_completion_consumer.get_async_db_session",
            new=lambda: _SingleSessionAsyncIterable(mock_db_session),
        ),
        patch(
            "src.services.pipeline_orchestrator_service.app.consumers.financial_reconciliation_completion_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.pipeline_orchestrator_service.app.consumers.financial_reconciliation_completion_consumer.PipelineOrchestratorService",
            return_value=mock_service,
        ),
        patch(
            "src.services.pipeline_orchestrator_service.app.consumers.financial_reconciliation_completion_consumer.PipelineStageRepository",
            return_value=SimpleNamespace(),
        ),
        patch(
            "src.services.pipeline_orchestrator_service.app.consumers.financial_reconciliation_completion_consumer.OutboxRepository",
            return_value=SimpleNamespace(),
        ),
    ):
        yield {
            "idempotency_repo": mock_idempotency_repo,
            "service": mock_service,
            "db_session": mock_db_session,
        }


async def test_completion_consumer_updates_orchestrator_stage_and_marks_idempotency(
    consumer: consumer_module.FinancialReconciliationCompletionConsumer,
    mock_kafka_message: MagicMock,
    mock_event: FinancialReconciliationCompletedEvent,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_service = mock_dependencies["service"]
    mock_idempotency_repo.is_event_processed.return_value = False

    await consumer.process_message(mock_kafka_message)

    mock_service.register_financial_reconciliation_completed.assert_awaited_once_with(
        mock_event,
        "corr-ctrl",
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once_with(
        "financial_reconciliation_completed-0-9",
        mock_event.portfolio_id,
        consumer_module.SERVICE_NAME,
        "corr-ctrl",
    )


async def test_completion_consumer_sends_invalid_payload_to_dlq(
    consumer: consumer_module.FinancialReconciliationCompletionConsumer,
):
    msg = MagicMock()
    msg.value.return_value = json.dumps({"portfolio_id": "bad"}).encode("utf-8")
    msg.key.return_value = b"bad"
    msg.topic.return_value = "financial_reconciliation_completed"
    msg.partition.return_value = 0
    msg.offset.return_value = 10
    msg.headers.return_value = []

    await consumer.process_message(msg)

    consumer._send_to_dlq_async.assert_awaited_once()
