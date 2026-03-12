# tests/unit/libs/portfolio-common/test_reprocessing_repository.py
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.reprocessing_repository import ReprocessingRepository
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    return MagicMock(spec=KafkaProducer)


@pytest.fixture
def repository(
    mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
) -> ReprocessingRepository:
    """Provides an instance of the ReprocessingRepository with mock dependencies."""
    return ReprocessingRepository(db=mock_db_session, kafka_producer=mock_kafka_producer)


async def test_reprocess_transactions_by_ids_success(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN a list of valid transaction IDs that exist in the database
    WHEN reprocess_transactions_by_ids is called
    THEN it should fetch the transactions and republish them to the correct Kafka topic.
    """
    # ARRANGE
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN1",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),  # FIX: Provide a valid default value
        )
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_transactions
    mock_db_session.execute.return_value = mock_result

    # ACT
    count = await repository.reprocess_transactions_by_ids(transaction_ids=["TXN1"])

    # ASSERT
    assert count == 1
    mock_db_session.execute.assert_awaited_once()

    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs

    assert call_args["topic"] == KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
    assert call_args["key"] == "P1"
    assert call_args["value"]["transaction_id"] == "TXN1"

    mock_kafka_producer.flush.assert_called_once()


async def test_reprocess_no_transactions_found(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN a list of transaction IDs that do not exist in the database
    WHEN reprocess_transactions_by_ids is called
    THEN it should not publish any messages and return 0.
    """
    # ARRANGE
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []  # No transactions found
    mock_db_session.execute.return_value = mock_result

    # ACT
    count = await repository.reprocess_transactions_by_ids(transaction_ids=["TXN_NOT_FOUND"])

    # ASSERT
    assert count == 0
    mock_db_session.execute.assert_awaited_once()
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_preserves_requested_input_order(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN multiple matching transactions
    WHEN reprocess_transactions_by_ids is called
    THEN the repository should republish them in the same deterministic order
    requested by the caller.
    """
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN_B",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
        DBTransaction(
            transaction_id="TXN_A",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_transactions
    mock_db_session.execute.return_value = mock_result

    count = await repository.reprocess_transactions_by_ids(transaction_ids=["TXN_B", "TXN_A"])

    assert count == 2
    published_ids = [
        call.kwargs["value"]["transaction_id"]
        for call in mock_kafka_producer.publish_message.call_args_list
    ]
    assert published_ids == ["TXN_B", "TXN_A"]


async def test_reprocess_transactions_deduplicates_requested_ids(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN duplicate transaction IDs in the caller request
    WHEN reprocess_transactions_by_ids is called
    THEN each canonical transaction should be republished only once, preserving first-seen order.
    """
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN_B",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
        DBTransaction(
            transaction_id="TXN_A",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_transactions
    mock_db_session.execute.return_value = mock_result

    count = await repository.reprocess_transactions_by_ids(
        transaction_ids=["TXN_B", "TXN_A", "TXN_B", "TXN_A"]
    )

    assert count == 2
    published_ids = [
        call.kwargs["value"]["transaction_id"]
        for call in mock_kafka_producer.publish_message.call_args_list
    ]
    assert published_ids == ["TXN_B", "TXN_A"]
