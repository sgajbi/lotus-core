# tests/unit/services/persistence_service/consumers/test_persistence_fx_rate_consumer.py
import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import FxRateEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.consumers.fx_rate_consumer import FxRateConsumer
from src.services.persistence_service.app.repositories.fx_rate_repository import FxRateRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fx_rate_consumer() -> FxRateConsumer:
    return FxRateConsumer(
        bootstrap_servers="mock_server",
        topic="fx_rates.raw.received",
        group_id="test_group",
        dlq_topic="dlq.persistence_service",
    )


@pytest.fixture
def valid_fx_rate_event() -> FxRateEvent:
    return FxRateEvent(
        from_currency="EUR",
        to_currency="USD",
        rate_date=date(2026, 5, 28),
        rate=Decimal("1.0875000000"),
    )


@pytest.fixture
def mock_kafka_message(valid_fx_rate_event: FxRateEvent) -> MagicMock:
    mock_message = MagicMock()
    mock_message.value.return_value = valid_fx_rate_event.model_dump_json().encode("utf-8")
    mock_message.key.return_value = b"EUR-USD-2026-05-28"
    mock_message.error.return_value = None
    mock_message.topic.return_value = "fx_rates.raw.received"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 1
    mock_message.headers.return_value = [("correlation_id", b"test-corr-id")]
    return mock_message


@pytest.fixture
def mock_dependencies():
    mock_repo = AsyncMock(spec=FxRateRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value = AsyncMock()

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.persistence_service.app.consumers.fx_rate_consumer.FxRateRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
        }


async def test_process_message_success(
    fx_rate_consumer: FxRateConsumer,
    mock_kafka_message: MagicMock,
    valid_fx_rate_event: FxRateEvent,
    mock_dependencies: dict,
) -> None:
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = True

    with patch.object(
        fx_rate_consumer, "_send_to_dlq_async", new_callable=AsyncMock
    ) as mock_send_to_dlq:
        await fx_rate_consumer.process_message(mock_kafka_message)

    mock_repo.upsert_fx_rate.assert_called_once_with(valid_fx_rate_event)
    mock_idempotency_repo.claim_event_processing.assert_awaited_once_with(
        "fx_rates.raw.received-0-1",
        "N/A",
        "persistence-fx-rates",
        "test-corr-id",
    )
    mock_send_to_dlq.assert_not_called()


async def test_process_message_sends_nonpositive_fx_rate_to_dlq(
    fx_rate_consumer: FxRateConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
) -> None:
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    incoming_event_dict = json.loads(mock_kafka_message.value().decode("utf-8"))
    incoming_event_dict["rate"] = "0"
    mock_kafka_message.value.return_value = json.dumps(incoming_event_dict).encode("utf-8")

    with patch.object(
        fx_rate_consumer, "_send_to_dlq_async", new_callable=AsyncMock
    ) as mock_send_to_dlq:
        with pytest.raises(ValueError, match="Poison pill"):
            await fx_rate_consumer.process_message(mock_kafka_message)

    mock_idempotency_repo.claim_event_processing.assert_not_called()
    mock_repo.upsert_fx_rate.assert_not_called()
    mock_send_to_dlq.assert_awaited_once()
