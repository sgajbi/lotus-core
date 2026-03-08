import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import FinancialReconciliationRequestedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.financial_reconciliation_service.app.consumers import (
    reconciliation_requested_consumer as consumer_module,
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
def consumer() -> consumer_module.ReconciliationRequestedConsumer:
    c = consumer_module.ReconciliationRequestedConsumer(
        bootstrap_servers="mock_server",
        topic="financial_reconciliation_requested",
        group_id="test_group",
    )
    c._send_to_dlq_async = AsyncMock()
    return c


@pytest.fixture
def mock_event() -> FinancialReconciliationRequestedEvent:
    return FinancialReconciliationRequestedEvent(
        portfolio_id="PORT-RECON-1",
        business_date=date(2026, 3, 8),
        epoch=1,
        correlation_id="corr-recon",
    )


@pytest.fixture
def mock_kafka_message(mock_event: FinancialReconciliationRequestedEvent) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    msg.key.return_value = b"PORT-RECON-1"
    msg.topic.return_value = "financial_reconciliation_requested"
    msg.partition.return_value = 0
    msg.offset.return_value = 7
    msg.headers.return_value = []
    return msg


@pytest.fixture
def mock_dependencies():
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_service = AsyncMock()
    mock_db_session = AsyncMock(spec=AsyncSession)

    with (
        patch(
            "src.services.financial_reconciliation_service.app.consumers.reconciliation_requested_consumer.get_async_db_session",
            new=lambda: _SingleSessionAsyncIterable(mock_db_session),
        ),
        patch(
            "src.services.financial_reconciliation_service.app.consumers.reconciliation_requested_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.financial_reconciliation_service.app.consumers.reconciliation_requested_consumer.ReconciliationService",
            return_value=mock_service,
        ),
        patch(
            "src.services.financial_reconciliation_service.app.consumers.reconciliation_requested_consumer.ReconciliationRepository",
        ),
    ):
        yield {
            "idempotency_repo": mock_idempotency_repo,
            "service": mock_service,
            "db_session": mock_db_session,
        }


async def test_reconciliation_request_runs_automatic_bundle_and_marks_idempotency(
    consumer: consumer_module.ReconciliationRequestedConsumer,
    mock_kafka_message: MagicMock,
    mock_event: FinancialReconciliationRequestedEvent,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_service = mock_dependencies["service"]
    mock_db_session = mock_dependencies["db_session"]
    mock_idempotency_repo.is_event_processed.return_value = False

    await consumer.process_message(mock_kafka_message)

    mock_service.run_automatic_bundle.assert_awaited_once()
    call = mock_service.run_automatic_bundle.await_args
    request = call.kwargs["request"]
    assert request.portfolio_id == mock_event.portfolio_id
    assert request.business_date == mock_event.business_date
    assert request.epoch == mock_event.epoch
    assert request.requested_by == mock_event.requested_by
    assert call.kwargs["reconciliation_types"] == mock_event.reconciliation_types

    mock_idempotency_repo.mark_event_processed.assert_awaited_once_with(
        "financial_reconciliation_requested-0-7",
        mock_event.portfolio_id,
        consumer_module.SERVICE_NAME,
        "corr-recon",
    )
    mock_db_session.commit.assert_awaited_once()


async def test_reconciliation_request_is_noop_when_already_processed(
    consumer: consumer_module.ReconciliationRequestedConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_service = mock_dependencies["service"]
    mock_idempotency_repo.is_event_processed.return_value = True

    await consumer.process_message(mock_kafka_message)

    mock_service.run_automatic_bundle.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()


async def test_invalid_reconciliation_request_payload_is_sent_to_dlq(
    consumer: consumer_module.ReconciliationRequestedConsumer,
):
    msg = MagicMock()
    msg.value.return_value = json.dumps({"portfolio_id": "bad"}).encode("utf-8")
    msg.key.return_value = b"bad"
    msg.topic.return_value = "financial_reconciliation_requested"
    msg.partition.return_value = 0
    msg.offset.return_value = 8
    msg.headers.return_value = []

    await consumer.process_message(msg)

    consumer._send_to_dlq_async.assert_awaited_once()
