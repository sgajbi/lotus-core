# tests/unit/services/ingestion-service/services/test_ingestion_service.py
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.logging_utils import correlation_id_var

from src.services.ingestion_service.app.DTOs.portfolio_bundle_dto import (
    PortfolioBundleIngestionRequest,
)
from src.services.ingestion_service.app.DTOs.portfolio_dto import Portfolio
from src.services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.ingestion_service.app.services.ingestion_service import IngestionService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    return MagicMock(spec=KafkaProducer)


@pytest.fixture
def ingestion_service(mock_kafka_producer: MagicMock) -> IngestionService:
    """Provides an IngestionService instance with a mocked producer."""
    return IngestionService(mock_kafka_producer)


async def test_publish_portfolios(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    """Verifies portfolios are published to the correct topic with portfolioId key."""
    # ARRANGE
    portfolios = [
        Portfolio(
            portfolio_id="P1",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    ]

    # ACT
    await ingestion_service.publish_portfolios(portfolios)

    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["topic"] == "raw_portfolios"
    assert call_args["key"] == "P1"
    assert call_args["value"]["portfolio_id"] == "P1"


async def test_publish_transactions(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    """Verifies transactions are published to the correct topic with portfolio_id key."""
    # ARRANGE
    transactions = [
        Transaction(
            transaction_id="T1",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=1,
            price=1,
            gross_transaction_amount=1,
            trade_currency="USD",
            currency="USD",
        )
    ]

    # ACT
    await ingestion_service.publish_transactions(transactions)

    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["topic"] == "raw_transactions"
    assert call_args["key"] == "P1"
    assert call_args["value"]["transaction_id"] == "T1"


async def test_publish_transactions_normalizes_partition_key(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    transactions = [
        Transaction(
            transaction_id="T2",
            portfolio_id="  P1  ",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=1,
            price=1,
            gross_transaction_amount=1,
            trade_currency="USD",
            currency="USD",
        )
    ]

    await ingestion_service.publish_transactions(transactions)

    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["key"] == "P1"


async def test_publish_transactions_rejects_empty_partition_key(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    transactions = [
        Transaction(
            transaction_id="T3",
            portfolio_id="   ",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=1,
            price=1,
            gross_transaction_amount=1,
            trade_currency="USD",
            currency="USD",
        )
    ]

    with pytest.raises(ValueError, match="portfolio_id"):
        await ingestion_service.publish_transactions(transactions)

    mock_kafka_producer.publish_message.assert_not_called()


async def test_publish_with_correlation_id(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    """Verifies that the correlation ID from the context is added to Kafka message headers."""
    # ARRANGE
    portfolios = [
        Portfolio(
            portfolio_id="P1",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    ]
    token = correlation_id_var.set("test-corr-id-123")

    # ACT
    try:
        await ingestion_service.publish_portfolios(portfolios)
    finally:
        correlation_id_var.reset(token)

    # ASSERT
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    headers = dict(call_args["headers"])
    assert headers["correlation_id"] == b"test-corr-id-123"


async def test_publish_with_idempotency_key(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    portfolios = [
        Portfolio(
            portfolio_id="P1",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    ]
    token = correlation_id_var.set("test-corr-id-123")
    try:
        await ingestion_service.publish_portfolios(
            portfolios, idempotency_key="portfolio-batch-key-001"
        )
    finally:
        correlation_id_var.reset(token)

    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    headers = dict(call_args["headers"])
    assert headers["correlation_id"] == b"test-corr-id-123"
    assert headers["idempotency_key"] == b"portfolio-batch-key-001"


async def test_publish_omits_not_set_correlation_header(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    portfolios = [
        Portfolio(
            portfolio_id="P1",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    ]
    token = correlation_id_var.set("<not-set>")
    try:
        await ingestion_service.publish_portfolios(portfolios)
    finally:
        correlation_id_var.reset(token)

    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["headers"] is None


async def test_publish_portfolio_bundle(ingestion_service: IngestionService):
    """Verifies mixed bundle fan-out returns correct published counts."""
    bundle = PortfolioBundleIngestionRequest.model_validate(
        {
            "business_dates": [{"business_date": "2026-01-02"}],
            "portfolios": [
                {
                    "portfolio_id": "P1",
                    "base_currency": "USD",
                    "open_date": "2025-01-01",
                    "client_id": "C1",
                    "status": "ACTIVE",
                    "risk_exposure": "a",
                    "investment_time_horizon": "b",
                    "portfolio_type": "c",
                    "booking_center_code": "d",
                }
            ],
            "instruments": [
                {
                    "security_id": "S1",
                    "name": "N1",
                    "isin": "I1",
                    "currency": "USD",
                    "product_type": "E",
                }
            ],
            "transactions": [
                {
                    "transaction_id": "T1",
                    "portfolio_id": "P1",
                    "instrument_id": "I1",
                    "security_id": "S1",
                    "transaction_date": "2026-01-02T10:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 1,
                    "price": 1,
                    "gross_transaction_amount": 1,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ],
            "market_prices": [
                {"security_id": "S1", "price_date": "2026-01-02", "price": 100, "currency": "USD"}
            ],
            "fx_rates": [
                {
                    "from_currency": "USD",
                    "to_currency": "EUR",
                    "rate_date": "2026-01-02",
                    "rate": 0.9,
                }
            ],
        }
    )

    counts = await ingestion_service.publish_portfolio_bundle(bundle)

    assert counts == {
        "business_dates": 1,
        "portfolios": 1,
        "instruments": 1,
        "transactions": 1,
        "market_prices": 1,
        "fx_rates": 1,
    }
