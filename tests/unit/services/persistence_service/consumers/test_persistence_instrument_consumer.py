from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import Instrument as DBInstrument
from portfolio_common.events import InstrumentEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.consumers.instrument_consumer import InstrumentConsumer
from src.services.persistence_service.app.repositories.instrument_repository import (
    InstrumentRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def instrument_consumer():
    return InstrumentConsumer(
        bootstrap_servers="mock_server",
        topic="instruments.received",
        group_id="test_group",
        dlq_topic="dlq.persistence_service",
    )


@pytest.fixture
def valid_instrument_event():
    return InstrumentEvent(
        security_id="CASH_USD_FX",
        name="US Dollar Cash",
        isin="CASH_USD_FX_E2E",
        currency="USD",
        product_type="Cash",
        asset_class="Cash",
        portfolio_id=None,
        trade_date=date(2026, 1, 1),
        maturity_date=None,
        pair_base_currency=None,
        pair_quote_currency=None,
        buy_currency=None,
        sell_currency=None,
        buy_amount=None,
        sell_amount=None,
        contract_rate=None,
    )


@pytest.fixture
def mock_kafka_message(valid_instrument_event: InstrumentEvent):
    mock_message = MagicMock()
    mock_message.value.return_value = valid_instrument_event.model_dump_json().encode("utf-8")
    mock_message.key.return_value = valid_instrument_event.security_id.encode("utf-8")
    mock_message.error.return_value = None
    mock_message.topic.return_value = "instruments.received"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 1
    mock_message.headers.return_value = [("correlation_id", b"test-corr-id")]
    return mock_message


@pytest.fixture
def mock_dependencies():
    mock_repo = AsyncMock(spec=InstrumentRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)

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
            "src.services.persistence_service.app.consumers.instrument_consumer.InstrumentRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
        }


async def test_process_message_success_without_portfolio_id(
    instrument_consumer: InstrumentConsumer,
    mock_kafka_message: MagicMock,
    valid_instrument_event: InstrumentEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.claim_event_processing.return_value = True
    mock_repo.create_or_update_instrument.return_value = DBInstrument(
        security_id=valid_instrument_event.security_id,
        name=valid_instrument_event.name,
        isin=valid_instrument_event.isin,
        currency=valid_instrument_event.currency,
        product_type=valid_instrument_event.product_type,
        asset_class=valid_instrument_event.asset_class,
        portfolio_id=None,
        trade_date=valid_instrument_event.trade_date,
        maturity_date=None,
        pair_base_currency=None,
        pair_quote_currency=None,
        buy_currency=None,
        sell_currency=None,
        buy_amount=None,
        sell_amount=None,
        contract_rate=None,
    )

    with patch.object(
        instrument_consumer, "_send_to_dlq_async", new_callable=AsyncMock
    ) as mock_send_to_dlq:
        await instrument_consumer.process_message(mock_kafka_message)

    mock_repo.create_or_update_instrument.assert_awaited_once_with(valid_instrument_event)
    mock_idempotency_repo.claim_event_processing.assert_awaited_once_with(
        "instruments.received-0-1",
        "N/A",
        "persistence-instruments",
        "test-corr-id",
    )
    mock_send_to_dlq.assert_not_called()


async def test_process_message_uses_header_correlation_on_direct_path(
    instrument_consumer: InstrumentConsumer,
    mock_kafka_message: MagicMock,
    valid_instrument_event: InstrumentEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.claim_event_processing.return_value = True
    mock_repo.create_or_update_instrument.return_value = DBInstrument(
        security_id=valid_instrument_event.security_id,
        name=valid_instrument_event.name,
        isin=valid_instrument_event.isin,
        currency=valid_instrument_event.currency,
        product_type=valid_instrument_event.product_type,
        asset_class=valid_instrument_event.asset_class,
        portfolio_id=None,
        trade_date=valid_instrument_event.trade_date,
        maturity_date=None,
        pair_base_currency=None,
        pair_quote_currency=None,
        buy_currency=None,
        sell_currency=None,
        buy_amount=None,
        sell_amount=None,
        contract_rate=None,
    )

    token = correlation_id_var.set("<not-set>")
    try:
        await instrument_consumer.process_message(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    mock_idempotency_repo.claim_event_processing.assert_awaited_once_with(
        "instruments.received-0-1",
        "N/A",
        "persistence-instruments",
        "test-corr-id",
    )
