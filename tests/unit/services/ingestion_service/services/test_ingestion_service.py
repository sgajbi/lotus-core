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
from src.services.ingestion_service.app.services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
)

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
    assert call_args["topic"] == "portfolios.raw.received"
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
    assert call_args["topic"] == "transactions.raw.received"
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


async def test_publish_transactions_reports_remaining_unpublished_keys_on_batch_failure(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
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
        ),
        Transaction(
            transaction_id="T2",
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
        ),
        Transaction(
            transaction_id="T3",
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
        ),
    ]
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]

    with pytest.raises(IngestionPublishError) as exc_info:
        await ingestion_service.publish_transactions(transactions)

    assert exc_info.value.failed_record_keys == ["T2", "T3"]
    assert exc_info.value.published_record_count == 1
    assert "Remaining unpublished record keys: T2, T3." in str(exc_info.value)


async def test_publish_reprocessing_requests_reports_remaining_unpublished_keys_on_batch_failure(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    transaction_ids = ["TX1", "TX2", "TX3"]
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]

    with pytest.raises(IngestionPublishError) as exc_info:
        await ingestion_service.publish_reprocessing_requests(transaction_ids)

    assert exc_info.value.failed_record_keys == ["TX2", "TX3"]
    assert exc_info.value.published_record_count == 1
    assert "Failed to publish reprocessing request 'TX2'" in str(exc_info.value)


async def test_publish_reprocessing_requests_fails_on_flush_timeout(
    ingestion_service: IngestionService, mock_kafka_producer: MagicMock
):
    transaction_ids = ["TX1", "TX2"]
    mock_kafka_producer.flush.return_value = 1

    with pytest.raises(IngestionPublishError) as exc_info:
        await ingestion_service.publish_reprocessing_requests(transaction_ids)

    assert exc_info.value.failed_record_keys == ["TX1", "TX2"]
    assert (
        "Delivery confirmation timed out for reprocessing request delivery confirmation."
        in str(exc_info.value)
    )


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


async def test_publish_portfolio_bundle_reports_completed_group_counts_before_failure(
    ingestion_service: IngestionService,
):
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
            "instruments": [],
            "transactions": [],
            "market_prices": [],
            "fx_rates": [],
        }
    )

    async def _ok_business_dates(*args, **kwargs):
        return None

    async def _fail_portfolios(*args, **kwargs):
        raise IngestionPublishError(
            "Failed to publish portfolio 'P1'.",
            failed_record_keys=["P1"],
        )

    ingestion_service.publish_business_dates = _ok_business_dates  # type: ignore[method-assign]
    ingestion_service.publish_portfolios = _fail_portfolios  # type: ignore[method-assign]

    with pytest.raises(IngestionPublishError) as exc_info:
        await ingestion_service.publish_portfolio_bundle(bundle)

    assert exc_info.value.failed_record_keys == ["P1"]
    assert (
        "Portfolio bundle publish stopped after these entity groups were already published: "
        "{'business_dates': 1, 'portfolios': 0, 'instruments': 0, 'transactions': 0, "
        "'market_prices': 0, 'fx_rates': 0}."
    ) in str(exc_info.value)
