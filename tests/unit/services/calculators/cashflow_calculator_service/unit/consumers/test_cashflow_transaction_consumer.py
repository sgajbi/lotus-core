# tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from datetime import datetime, date
from decimal import Decimal
from contextlib import asynccontextmanager
import json

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, CashflowCalculatedEvent
from portfolio_common.database_models import Cashflow, CashflowRule
from src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer import CashflowCalculatorConsumer, NoCashflowRuleError
from src.services.calculators.cashflow_calculator_service.app.repositories.cashflow_repository import CashflowRepository
from src.services.calculators.cashflow_calculator_service.app.repositories.cashflow_rules_repository import CashflowRulesRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from tests.unit.test_support.async_session_iter import make_single_session_getter

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
def reset_cache():
    """Resets the module-level cache before each test to ensure isolation."""
    from src.services.calculators.cashflow_calculator_service.app.consumers import transaction_consumer
    transaction_consumer._cashflow_rule_cache_state = None
    yield

@pytest.fixture
def cashflow_consumer():
    """Provides an instance of the consumer for testing."""
    consumer = CashflowCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions_completed",
        group_id="test_group",
        dlq_topic="test.dlq"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_kafka_message():
    """Creates a mock Kafka message containing a valid BUY transaction."""
    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_CONSUMER",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="BUY", # Default type
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5.50"),
        trade_currency="USD",
        currency="USD",
        epoch=1
    )
    
    mock_msg = MagicMock()
    mock_msg.value.return_value = event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = event.portfolio_id.encode('utf-8')
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 123
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = [('correlation_id', b'test-corr-id')]
    return mock_msg

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_cashflow_repo = AsyncMock(spec=CashflowRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    mock_rules_repo = AsyncMock(spec=CashflowRulesRepository) 
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin = AsyncMock(return_value=mock_transaction)
    
    get_session_gen = make_single_session_getter(mock_db_session)

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRepository", return_value=mock_cashflow_repo
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.OutboxRepository", return_value=mock_outbox_repo
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository", return_value=mock_rules_repo
    ):
        yield {
            "cashflow_repo": mock_cashflow_repo,
            "idempotency_repo": mock_idempotency_repo,
            "outbox_repo": mock_outbox_repo,
            "rules_repo": mock_rules_repo
        }

async def test_process_message_success(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a valid new transaction message
    WHEN the process_message method is called
    THEN it should check for idempotency, load rules, call the repository, and publish an event.
    """
    # Arrange
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    
    mock_rules_repo.get_all_rules.return_value = [
        CashflowRule(transaction_type='BUY', classification='INVESTMENT_OUTFLOW', timing='BOD', is_position_flow=True, is_portfolio_flow=False)
    ]
    
    mock_saved_cashflow = Cashflow(
        id=1, transaction_id="TXN_CASHFLOW_CONSUMER", portfolio_id="PORT_CFC_01",
        security_id="SEC_CFC_01", cashflow_date=date(2025, 8, 1),
        amount=Decimal("1005.50"), currency="USD", classification="INVESTMENT_OUTFLOW",
        timing="BOD", calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=1
    )
    mock_cashflow_repo.create_cashflow.return_value = mock_saved_cashflow

    with patch("src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer") as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance
        
        # Act
        await cashflow_consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once_with("raw_transactions_completed-0-123", "cashflow-calculator")
        mock_rules_repo.get_all_rules.assert_awaited_once()
        mock_cashflow_repo.create_cashflow.assert_called_once()
        mock_outbox_repo.create_outbox_event.assert_called_once()
        
        outbox_payload = mock_outbox_repo.create_outbox_event.call_args.kwargs['payload']
        assert outbox_payload['epoch'] == 1
        
        mock_idempotency_repo.mark_event_processed.assert_called_once()
        cashflow_consumer._send_to_dlq_async.assert_not_called()

async def test_process_message_sends_to_dlq_if_rule_not_found(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a transaction message for which no rule exists in the database
    WHEN the consumer processes it
    THEN it should raise NoCashflowRuleError and send the message to the DLQ.
    """
    # ARRANGE
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    
    # Simulate the repository returning an empty list of rules
    mock_rules_repo.get_all_rules.return_value = []
    
    with patch("src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer") as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        # ACT
        await cashflow_consumer.process_message(mock_kafka_message)

        # ASSERT
        # Missing-rule path intentionally forces one immediate refresh.
        assert mock_rules_repo.get_all_rules.await_count == 2
        
        # Verify business logic was NOT executed
        mock_cashflow_repo.create_cashflow.assert_not_called()
        mock_outbox_repo.create_outbox_event.assert_not_called()
        
        # Verify the message was sent to the DLQ
        cashflow_consumer._send_to_dlq_async.assert_awaited_once()
        dlq_error_arg = cashflow_consumer._send_to_dlq_async.call_args[0][1]
        assert isinstance(dlq_error_arg, NoCashflowRuleError)

async def test_process_message_skips_stale_epoch_event(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a transaction message that the EpochFencer flags as stale
    WHEN the process_message method is called
    THEN it should skip all business logic and publishing.
    """
    # Arrange
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    # Mock the fencer to return False, indicating a stale event
    with patch("src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer") as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = False
        mock_fencer_class.return_value = mock_fencer_instance

        # Act
        await cashflow_consumer.process_message(mock_kafka_message)

        # Assert
        mock_fencer_instance.check.assert_awaited_once()
        mock_idempotency_repo.is_event_processed.assert_not_called()
        mock_cashflow_repo.create_cashflow.assert_not_called()
        mock_outbox_repo.create_outbox_event.assert_not_called()
        cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_get_rule_for_transaction_uses_ttl_cache_then_refreshes(
    cashflow_consumer: CashflowCalculatorConsumer,
):
    from src.services.calculators.cashflow_calculator_service.app.consumers import transaction_consumer

    mock_db_session = AsyncMock(spec=AsyncSession)
    rules_repo = AsyncMock(spec=CashflowRulesRepository)
    rules_repo.get_all_rules.side_effect = [
        [
            CashflowRule(
                transaction_type="BUY",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                is_position_flow=True,
                is_portfolio_flow=False,
            )
        ],
        [
            CashflowRule(
                transaction_type="BUY",
                classification="INVESTMENT_OUTFLOW",
                timing="EOD",
                is_position_flow=True,
                is_portfolio_flow=False,
            )
        ],
    ]

    with patch.object(transaction_consumer, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 300), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
        return_value=rules_repo,
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.time.monotonic",
        side_effect=[10.0, 20.0, 1200.0, 1210.0],
    ):
        first_rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY")
        second_rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY")
        third_rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY")
        assert first_rule is not None
        assert second_rule is not None
        assert third_rule is not None
        assert first_rule.timing == "BOD"
        assert second_rule.timing == "BOD"
        assert third_rule.timing == "EOD"
        assert rules_repo.get_all_rules.await_count == 2


async def test_get_rule_for_transaction_missing_rule_forces_immediate_refresh(
    cashflow_consumer: CashflowCalculatorConsumer,
):
    from src.services.calculators.cashflow_calculator_service.app.consumers import transaction_consumer

    mock_db_session = AsyncMock(spec=AsyncSession)
    rules_repo = AsyncMock(spec=CashflowRulesRepository)
    rules_repo.get_all_rules.side_effect = [
        [
            CashflowRule(
                transaction_type="BUY",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                is_position_flow=True,
                is_portfolio_flow=False,
            )
        ],
        [
            CashflowRule(
                transaction_type="DIVIDEND",
                classification="INCOME",
                timing="EOD",
                is_position_flow=True,
                is_portfolio_flow=False,
            )
        ],
    ]

    with patch.object(transaction_consumer, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 300), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
        return_value=rules_repo,
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.time.monotonic",
        side_effect=[100.0, 110.0],
    ):
        rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "DIVIDEND")
        assert rule is not None
        assert rule.transaction_type == "DIVIDEND"
        assert rules_repo.get_all_rules.await_count == 2


async def test_invalidate_cashflow_rule_cache_forces_reload(
    cashflow_consumer: CashflowCalculatorConsumer,
):
    from src.services.calculators.cashflow_calculator_service.app.consumers import transaction_consumer

    mock_db_session = AsyncMock(spec=AsyncSession)
    rules_repo = AsyncMock(spec=CashflowRulesRepository)
    rules_repo.get_all_rules.side_effect = [
        [
            CashflowRule(
                transaction_type="BUY",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                is_position_flow=True,
                is_portfolio_flow=False,
            )
        ],
        [
            CashflowRule(
                transaction_type="BUY",
                classification="INVESTMENT_OUTFLOW",
                timing="EOD",
                is_position_flow=True,
                is_portfolio_flow=False,
            )
        ],
    ]

    with patch.object(transaction_consumer, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 3600), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
        return_value=rules_repo,
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.time.monotonic",
        side_effect=[5.0, 6.0, 7.0, 8.0],
    ):
        first_rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY")
        assert first_rule is not None
        assert first_rule.timing == "BOD"
        transaction_consumer.invalidate_cashflow_rule_cache()
        reloaded_rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY")
        assert reloaded_rule is not None
        assert reloaded_rule.timing == "EOD"
        assert rules_repo.get_all_rules.await_count == 2
