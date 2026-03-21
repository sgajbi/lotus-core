# tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py  # noqa: E501
import asyncio
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import Cashflow, CashflowRule
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer import (  # noqa: E501
    CachedCashflowRule,
    CashflowCalculatorConsumer,
    LinkedCashLegError,
    NoCashflowRuleError,
)
from src.services.calculators.cashflow_calculator_service.app.repositories.cashflow_repository import (  # noqa: E501
    CashflowRepository,
)
from src.services.calculators.cashflow_calculator_service.app.repositories.cashflow_rules_repository import (  # noqa: E501
    CashflowRulesRepository,
)
from tests.unit.test_support.async_session_iter import make_single_session_getter

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_cache():
    """Resets the module-level cache before each test to ensure isolation."""
    from src.services.calculators.cashflow_calculator_service.app.consumers import (
        transaction_consumer,
    )

    transaction_consumer._cashflow_rule_cache_state = None
    transaction_consumer._cashflow_rule_cache_lock = None
    yield


@pytest.fixture
def cashflow_consumer():
    """Provides an instance of the consumer for testing."""
    consumer = CashflowCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.persisted",
        group_id="test_group",
        dlq_topic="test.dlq",
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
        transaction_type="BUY",  # Default type
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5.50"),
        trade_currency="USD",
        currency="USD",
        epoch=1,
    )

    mock_msg = MagicMock()
    mock_msg.value.return_value = event.model_dump_json().encode("utf-8")
    mock_msg.key.return_value = event.portfolio_id.encode("utf-8")
    mock_msg.topic.return_value = "transactions.persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 123
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = [("correlation_id", b"test-corr-id")]
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

    with (
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRepository",
            return_value=mock_cashflow_repo,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
            return_value=mock_rules_repo,
        ),
    ):
        yield {
            "cashflow_repo": mock_cashflow_repo,
            "idempotency_repo": mock_idempotency_repo,
            "outbox_repo": mock_outbox_repo,
            "rules_repo": mock_rules_repo,
        }


async def test_process_message_success(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
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
        CashflowRule(
            transaction_type="BUY",
            classification="INVESTMENT_OUTFLOW",
            timing="BOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    ]

    mock_saved_cashflow = Cashflow(
        id=1,
        transaction_id="TXN_CASHFLOW_CONSUMER",
        portfolio_id="PORT_CFC_01",
        security_id="SEC_CFC_01",
        cashflow_date=date(2025, 8, 1),
        amount=Decimal("1005.50"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=1,
    )
    mock_cashflow_repo.create_cashflow.return_value = mock_saved_cashflow

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        # Act
        await cashflow_consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once_with(
            "transactions.persisted-0-123", "cashflow-calculator"
        )
        mock_rules_repo.get_all_rules.assert_awaited_once()
        mock_cashflow_repo.create_cashflow.assert_called_once()
        mock_outbox_repo.create_outbox_event.assert_called_once()

        outbox_payload = mock_outbox_repo.create_outbox_event.call_args.kwargs["payload"]
        assert outbox_payload["epoch"] == 1
        assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
            "test-corr-id"
        )

        mock_idempotency_repo.mark_event_processed.assert_called_once()
        assert mock_idempotency_repo.mark_event_processed.call_args.args[3] == "test-corr-id"
        cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_process_message_sends_to_dlq_if_rule_not_found(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
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

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
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
    mock_dependencies: dict,
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
    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
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


async def test_process_message_skips_replay_event_when_canonical_state_was_removed(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    """
    GIVEN a replay cashflow event that arrives after its canonical transaction/portfolio
    state has been removed
    WHEN the consumer processes the message
    THEN it should acknowledge and skip the stale replay instead of retrying forever.
    """
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    mock_kafka_message.topic.return_value = "transactions.cost.processed"
    mock_idempotency_repo.is_event_processed.return_value = False
    mock_cashflow_repo.portfolio_exists.return_value = False
    mock_cashflow_repo.transaction_exists.return_value = False

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_cashflow_repo.portfolio_exists.assert_awaited_once_with("PORT_CFC_01")
    mock_cashflow_repo.transaction_exists.assert_awaited_once_with(
        "TXN_CASHFLOW_CONSUMER", portfolio_id="PORT_CFC_01"
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
    mock_idempotency_repo.is_event_processed.assert_not_called()
    mock_rules_repo.get_all_rules.assert_not_awaited()
    mock_cashflow_repo.create_cashflow.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
    cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_get_rule_for_transaction_uses_ttl_cache_then_refreshes(
    cashflow_consumer: CashflowCalculatorConsumer,
):
    from src.services.calculators.cashflow_calculator_service.app.consumers import (
        transaction_consumer,
    )

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

    with (
        patch.object(transaction_consumer, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 300),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
            return_value=rules_repo,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.time.monotonic",
            side_effect=[10.0, 11.0, 400.0, 401.0, 402.0, 403.0],
        ),
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
    from src.services.calculators.cashflow_calculator_service.app.consumers import (
        transaction_consumer,
    )

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

    with (
        patch.object(transaction_consumer, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 300),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
            return_value=rules_repo,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.time.monotonic",
            side_effect=[100.0, 110.0],
        ),
    ):
        rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "DIVIDEND")
        assert rule is not None
        assert rule.classification == "INCOME"
        assert isinstance(rule, CachedCashflowRule)
        assert rules_repo.get_all_rules.await_count == 2


async def test_invalidate_cashflow_rule_cache_forces_reload(
    cashflow_consumer: CashflowCalculatorConsumer,
):
    from src.services.calculators.cashflow_calculator_service.app.consumers import (
        transaction_consumer,
    )

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

    with (
        patch.object(transaction_consumer, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 3600),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
            return_value=rules_repo,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.time.monotonic",
            side_effect=[5.0, 6.0, 7.0, 8.0],
        ),
    ):
        first_rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY")
        assert first_rule is not None
        assert first_rule.timing == "BOD"
        transaction_consumer.invalidate_cashflow_rule_cache()
        reloaded_rule = await cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY")
        assert reloaded_rule is not None
        assert reloaded_rule.timing == "EOD"
        assert rules_repo.get_all_rules.await_count == 2


async def test_load_cashflow_rules_cache_returns_session_safe_rule_snapshots(
    cashflow_consumer: CashflowCalculatorConsumer,
):
    mock_db_session = AsyncMock(spec=AsyncSession)
    rules_repo = AsyncMock(spec=CashflowRulesRepository)
    rules_repo.get_all_rules.return_value = [
        CashflowRule(
            transaction_type="FX_CASH_SETTLEMENT_BUY",
            classification="FX_BUY",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    ]

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
        return_value=rules_repo,
    ):
        cache_state = await cashflow_consumer._load_cashflow_rules_cache(mock_db_session)

    rule = cache_state.rules_by_transaction_type["FX_CASH_SETTLEMENT_BUY"]
    assert isinstance(rule, CachedCashflowRule)
    assert rule.classification == "FX_BUY"
    assert rule.timing == "EOD"


async def test_process_message_skips_non_cash_fx_contract_lifecycle_components(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_FX_CONTRACT_01",
        portfolio_id="PORT_CFC_01",
        instrument_id="FXC-2026-0001",
        security_id="FXC-2026-0001",
        transaction_date=datetime(2026, 1, 2, 10, 0, 0),
        settlement_date=datetime(2026, 7, 1, 10, 0, 0),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        fx_contract_id="FXC-2026-0001",
        fx_contract_open_transaction_id="TXN_CASHFLOW_FX_CONTRACT_01",
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")
    mock_idempotency_repo.is_event_processed.return_value = False

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_not_awaited()
    mock_cashflow_repo.create_cashflow.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
    cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_process_message_dividend_external_mode_still_creates_product_cashflow(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_DIV_EXT_01",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="CASH_EXT_01",
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_rules_repo.get_all_rules.return_value = [
        CashflowRule(
            transaction_type="DIVIDEND",
            classification="INCOME",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    ]
    mock_cashflow_repo.create_cashflow.return_value = Cashflow(
        id=21,
        transaction_id=event.transaction_id,
        portfolio_id=event.portfolio_id,
        security_id=event.security_id,
        cashflow_date=date(2025, 8, 1),
        amount=Decimal("1000"),
        currency="USD",
        classification="INCOME",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=1,
    )

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_awaited_once()
    mock_cashflow_repo.create_cashflow.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
    cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_process_message_dividend_external_mode_without_link_sends_to_dlq(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_DIV_EXT_02",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=None,
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_not_awaited()
    mock_cashflow_repo.create_cashflow.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()
    cashflow_consumer._send_to_dlq_async.assert_awaited_once()
    dlq_error_arg = cashflow_consumer._send_to_dlq_async.call_args[0][1]
    assert isinstance(dlq_error_arg, LinkedCashLegError)


async def test_process_message_interest_external_mode_still_creates_product_cashflow(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_INT_EXT_01",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="INTEREST",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="CASH_INT_EXT_01",
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_rules_repo.get_all_rules.return_value = [
        CashflowRule(
            transaction_type="INTEREST",
            classification="INCOME",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    ]
    mock_cashflow_repo.create_cashflow.return_value = Cashflow(
        id=22,
        transaction_id=event.transaction_id,
        portfolio_id=event.portfolio_id,
        security_id=event.security_id,
        cashflow_date=date(2025, 8, 1),
        amount=Decimal("1000"),
        currency="USD",
        classification="INCOME",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=1,
    )

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_awaited_once()
    mock_cashflow_repo.create_cashflow.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
    cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_process_message_interest_external_mode_without_link_sends_to_dlq(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_INT_EXT_02",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="INTEREST",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=None,
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_not_awaited()
    mock_cashflow_repo.create_cashflow.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()
    cashflow_consumer._send_to_dlq_async.assert_awaited_once()
    dlq_error_arg = cashflow_consumer._send_to_dlq_async.call_args[0][1]
    assert isinstance(dlq_error_arg, LinkedCashLegError)


async def test_process_message_buy_with_linked_cash_leg_still_creates_product_cashflow(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_BUY_LINKED_01",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        external_cash_transaction_id="TXN_CASHFLOW_BUY_LINKED_01-CASHLEG",
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_rules_repo.get_all_rules.return_value = [
        CashflowRule(
            transaction_type="BUY",
            classification="INVESTMENT_OUTFLOW",
            timing="BOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    ]
    mock_cashflow_repo.create_cashflow.return_value = Cashflow(
        id=23,
        transaction_id=event.transaction_id,
        portfolio_id=event.portfolio_id,
        security_id=event.security_id,
        cashflow_date=date(2025, 8, 1),
        amount=Decimal("-1005"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=1,
    )

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_awaited_once()
    mock_cashflow_repo.create_cashflow.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
    cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_process_message_cash_in_lieu_with_linked_cash_leg_still_creates_product_cashflow(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_CIL_LINKED_01",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="CASH_IN_LIEU",
        quantity=Decimal("0.5"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("110"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        external_cash_transaction_id="TXN_CASHFLOW_CIL_LINKED_01-CASHLEG",
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")
    mock_idempotency_repo.is_event_processed.return_value = False
    mock_rules_repo.get_all_rules.return_value = [
        CashflowRule(
            transaction_type="CASH_IN_LIEU",
            classification="INCOME",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    ]
    mock_cashflow_repo.create_cashflow.return_value = Cashflow(
        id=99,
        transaction_id="TXN_CASHFLOW_CIL_LINKED_01",
        portfolio_id="PORT_CFC_01",
        security_id="SEC_CFC_01",
        cashflow_date=date(2025, 8, 1),
        amount=Decimal("110"),
        currency="USD",
        classification="INCOME",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=1,
    )

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_awaited_once()
    mock_cashflow_repo.create_cashflow.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
    cashflow_consumer._send_to_dlq_async.assert_not_called()


async def test_process_message_fee_auto_generate_mode_sends_to_dlq(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_FEE_AUTO_01",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="FEE",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("12"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")
    mock_idempotency_repo.is_event_processed.return_value = False

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_not_awaited()
    mock_cashflow_repo.create_cashflow.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()
    cashflow_consumer._send_to_dlq_async.assert_awaited_once()


async def test_process_message_cash_consideration_missing_parent_reference_sends_to_dlq(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_rules_repo = mock_dependencies["rules_repo"]

    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_CA_INVALID_01",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="CASH_CONSIDERATION",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("100"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        parent_event_reference=None,
        economic_event_id="EVT-CA-01",
        linked_transaction_group_id="LTG-CA-01",
        linked_cash_transaction_id="CASH_LEG_01",
        epoch=1,
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode("utf-8")
    mock_idempotency_repo.is_event_processed.return_value = False

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance
        await cashflow_consumer.process_message(mock_kafka_message)

    mock_rules_repo.get_all_rules.assert_not_awaited()
    mock_cashflow_repo.create_cashflow.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()
    cashflow_consumer._send_to_dlq_async.assert_awaited_once()


async def test_get_rule_for_transaction_concurrent_refresh_loads_rules_once(
    cashflow_consumer: CashflowCalculatorConsumer,
):
    from src.services.calculators.cashflow_calculator_service.app.consumers import (
        transaction_consumer,
    )

    mock_db_session = AsyncMock(spec=AsyncSession)
    rules_repo = AsyncMock(spec=CashflowRulesRepository)
    rules_repo.get_all_rules.return_value = [
        CashflowRule(
            transaction_type="BUY",
            classification="INVESTMENT_OUTFLOW",
            timing="BOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    ]

    with (
        patch.object(transaction_consumer, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 3600),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRulesRepository",
            return_value=rules_repo,
        ),
        patch(
            "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.time.monotonic",
            side_effect=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        ),
    ):
        results = await asyncio.gather(
            cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY"),
            cashflow_consumer._get_rule_for_transaction(mock_db_session, "BUY"),
        )
        assert results[0] is not None
        assert results[1] is not None
        assert rules_repo.get_all_rules.await_count == 1
