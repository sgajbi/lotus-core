from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import MarketPricePersistedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.consumers.price_event_consumer import (
    PriceEventConsumer,
)
from src.services.valuation_orchestrator_service.app.repositories import (
    instrument_reprocessing_state_repository as instrument_reprocessing_state_repo,
)
from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> PriceEventConsumer:
    consumer = PriceEventConsumer(
        bootstrap_servers="mock_server",
        topic="market_prices.persisted",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_event() -> MarketPricePersistedEvent:
    return MarketPricePersistedEvent(
        security_id="SEC_TEST_PRICE_EVENT",
        price_date=date(2025, 8, 5),
        price=150.0,
        currency="USD",
    )


@pytest.fixture
def mock_kafka_message(mock_event: MarketPricePersistedEvent) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    mock_msg.key.return_value = mock_event.security_id.encode("utf-8")
    mock_msg.topic.return_value = "market_prices.persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.headers.return_value = []
    return mock_msg


@pytest.fixture
def mock_dependencies():
    mock_valuation_repo = AsyncMock(spec=ValuationRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_reprocessing_repo = AsyncMock(
        spec=instrument_reprocessing_state_repo.InstrumentReprocessingStateRepository
    )
    mock_job_repo = AsyncMock(spec=ValuationJobRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value = AsyncMock()

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.price_event_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.price_event_consumer.ValuationRepository",
            return_value=mock_valuation_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.price_event_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.price_event_consumer.InstrumentReprocessingStateRepository",
            return_value=mock_reprocessing_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.price_event_consumer.ValuationJobRepository",
            return_value=mock_job_repo,
        ),
    ):
        yield {
            "valuation_repo": mock_valuation_repo,
            "idempotency_repo": mock_idempotency_repo,
            "reprocessing_repo": mock_reprocessing_repo,
            "job_repo": mock_job_repo,
        }


async def test_backdated_price_flags_instrument_for_reprocessing(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date + timedelta(
        days=5
    )

    await consumer.process_message(mock_kafka_message)

    mock_reprocessing_repo.upsert_state.assert_awaited_once_with(
        security_id=mock_event.security_id,
        price_date=mock_event.price_date,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()


async def test_current_price_does_not_flag_instrument(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date

    await consumer.process_message(mock_kafka_message)

    mock_reprocessing_repo.upsert_state.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()


async def test_current_price_without_ready_open_positions_stages_reprocessing(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date
    mock_valuation_repo.find_open_position_keys_for_security_on_date.return_value = []

    await consumer.process_message(mock_kafka_message)

    mock_job_repo.upsert_job.assert_not_called()
    mock_reprocessing_repo.upsert_state.assert_awaited_once_with(
        security_id=mock_event.security_id,
        price_date=mock_event.price_date,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()


async def test_future_dated_price_stages_deferred_reprocessing(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date - timedelta(
        days=1
    )

    await consumer.process_message(mock_kafka_message)

    mock_job_repo.upsert_job.assert_not_called()
    mock_reprocessing_repo.upsert_state.assert_awaited_once_with(
        security_id=mock_event.security_id,
        price_date=mock_event.price_date,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()


async def test_price_without_business_date_stages_deferred_reprocessing(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = None

    await consumer.process_message(mock_kafka_message)

    mock_job_repo.upsert_job.assert_not_called()
    mock_reprocessing_repo.upsert_state.assert_awaited_once_with(
        security_id=mock_event.security_id,
        price_date=mock_event.price_date,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()


async def test_current_price_queues_immediate_jobs_for_open_positions(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date
    mock_valuation_repo.find_open_position_keys_for_security_on_date.return_value = [
        ("P1", mock_event.security_id, 0),
        ("P2", mock_event.security_id, 1),
    ]

    await consumer.process_message(mock_kafka_message)

    assert mock_job_repo.upsert_job.await_count == 2
    mock_job_repo.upsert_job.assert_any_await(
        portfolio_id="P1",
        security_id=mock_event.security_id,
        valuation_date=mock_event.price_date,
        epoch=0,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )
    mock_job_repo.upsert_job.assert_any_await(
        portfolio_id="P2",
        security_id=mock_event.security_id,
        valuation_date=mock_event.price_date,
        epoch=1,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )


async def test_backdated_price_queues_current_date_job_and_flags_reprocessing(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date + timedelta(
        days=2
    )
    mock_valuation_repo.find_open_position_keys_for_security_on_date.return_value = [
        ("P1", mock_event.security_id, 0)
    ]

    await consumer.process_message(mock_kafka_message)

    mock_job_repo.upsert_job.assert_awaited_once_with(
        portfolio_id="P1",
        security_id=mock_event.security_id,
        valuation_date=mock_event.price_date,
        epoch=0,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )
    mock_reprocessing_repo.upsert_state.assert_awaited_once_with(
        security_id=mock_event.security_id,
        price_date=mock_event.price_date,
        correlation_id=f"PRICE_EVENT_{mock_event.security_id}_{mock_event.price_date.isoformat()}",
    )


async def test_price_event_uses_header_correlation_for_direct_processing(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date
    mock_valuation_repo.find_open_position_keys_for_security_on_date.return_value = [
        ("P1", mock_event.security_id, 0)
    ]
    mock_kafka_message.headers.return_value = [("correlation_id", b"test-corr-id")]

    await consumer.process_message(mock_kafka_message)

    assert mock_job_repo.upsert_job.await_args.kwargs["correlation_id"] == "test-corr-id"
    assert mock_idempotency_repo.mark_event_processed.await_args.args[3] == "test-corr-id"
