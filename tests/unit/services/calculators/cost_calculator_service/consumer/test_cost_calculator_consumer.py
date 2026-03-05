# tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py
import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.models.transaction import Transaction as EngineTransaction
from portfolio_common.database_models import Portfolio
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.transaction_domain import (
    DIVIDEND_DEFAULT_POLICY_ID,
    DIVIDEND_DEFAULT_POLICY_VERSION,
    INTEREST_DEFAULT_POLICY_ID,
    INTEREST_DEFAULT_POLICY_VERSION,
    SELL_AVCO_POLICY_ID,
    SELL_DEFAULT_POLICY_VERSION,
    SELL_FIFO_POLICY_ID,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cost_calculator_service.app.consumer import (
    CostCalculatorConsumer,
    PortfolioNotFoundError,
)
from src.services.calculators.cost_calculator_service.app.repository import CostCalculatorRepository
from tests.unit.test_support.async_session_iter import make_single_session_getter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def cost_calculator_consumer():
    """
    Provides an instance of the consumer.
    """
    consumer = CostCalculatorConsumer(
        bootstrap_servers="mock_server", topic="raw_transactions_completed", group_id="test_group"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_repo = AsyncMock(spec=CostCalculatorRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction

    get_session_gen = make_single_session_getter(mock_db_session)

    with (
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.CostCalculatorRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
            "outbox_repo": mock_outbox_repo,
        }


@pytest.fixture
def mock_sell_kafka_message():
    """Provides a reusable mock Kafka message for a SELL transaction."""
    sell_event = TransactionEvent(
        transaction_id="SELL01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 20),
        transaction_type="SELL",
        quantity=Decimal("10"),
        price=Decimal("175.0"),
        gross_transaction_amount=Decimal("1750.0"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("0.0"),
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = sell_event.model_dump_json().encode("utf-8")
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.headers.return_value = []
    return mock_msg


@pytest.fixture
def mock_buy_kafka_message() -> MagicMock:
    """Creates a mock Kafka message for a BUY transaction with a fee."""
    buy_event = TransactionEvent(
        transaction_id="BUY_WITH_FEE_01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 15),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"),
        trade_fee=Decimal("7.50"),
        trade_currency="USD",
        currency="USD",
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = buy_event.model_dump_json().encode("utf-8")
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 2
    mock_msg.headers.return_value = []
    return mock_msg


@pytest.fixture
def mock_dividend_kafka_message() -> MagicMock:
    """Provides a reusable mock Kafka message for a DIVIDEND transaction."""
    dividend_event = TransactionEvent(
        transaction_id="DIV01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 25),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("120.0"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("0.0"),
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = dividend_event.model_dump_json().encode("utf-8")
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 3
    mock_msg.headers.return_value = []
    return mock_msg


@pytest.fixture
def mock_interest_kafka_message() -> MagicMock:
    """Provides a reusable mock Kafka message for an INTEREST transaction."""
    interest_event = TransactionEvent(
        transaction_id="INT01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 26),
        transaction_type="INTEREST",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("95.0"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("0.0"),
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = interest_event.model_dump_json().encode("utf-8")
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 4
    mock_msg.headers.return_value = []
    return mock_msg


async def test_consumer_integration_with_engine(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_sell_kafka_message: MagicMock,
    mock_dependencies,
):
    """
    GIVEN a new SELL transaction message
    WHEN the consumer processes it, using the real TransactionProcessor
    THEN it should fetch history, calculate the realized P&L, and update the database.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    buy_history = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        security_id="SEC_COST_01",
        instrument_id="AAPL",
        transaction_type="BUY",
        transaction_date=datetime(2025, 1, 10),
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("1500"),
        net_cost_local=Decimal("1500"),
        transaction_fx_rate=Decimal("1.0"),
        trade_fee=Decimal("0.0"),
    )
    mock_repo.get_transaction_history.return_value = [buy_history]
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None
    mock_idempotency_repo.is_event_processed.return_value = False

    def create_db_tx(engine_txn: EngineTransaction) -> DBTransaction:
        data = engine_txn.model_dump(exclude_none=True)
        data.pop("portfolio_base_currency", None)
        data.pop("fees", None)
        data.pop("accrued_interest", None)
        data.pop("epoch", None)
        data.pop("net_transaction_amount", None)
        data.pop("average_price", None)
        data.pop("error_reason", None)
        return DBTransaction(**data)

    mock_repo.update_transaction_costs.side_effect = create_db_tx

    # ACT
    await cost_calculator_consumer.process_message(mock_sell_kafka_message)

    # ASSERT
    mock_idempotency_repo.is_event_processed.assert_called_once()
    mock_repo.get_transaction_history.assert_called_once()
    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]
    assert isinstance(updated_transaction_arg, EngineTransaction)
    assert updated_transaction_arg.realized_gain_loss == Decimal("250.0")
    assert updated_transaction_arg.economic_event_id == "EVT-SELL-PORT_COST_01-SELL01"
    assert updated_transaction_arg.linked_transaction_group_id == "LTG-SELL-PORT_COST_01-SELL01"
    assert updated_transaction_arg.calculation_policy_id == SELL_FIFO_POLICY_ID
    assert updated_transaction_arg.calculation_policy_version == SELL_DEFAULT_POLICY_VERSION
    mock_outbox_repo.create_outbox_event.assert_called_once()
    payload = mock_outbox_repo.create_outbox_event.call_args.kwargs["payload"]
    assert payload["economic_event_id"] == "EVT-SELL-PORT_COST_01-SELL01"
    assert payload["linked_transaction_group_id"] == "LTG-SELL-PORT_COST_01-SELL01"
    mock_repo.upsert_buy_lot_state.assert_not_called()
    mock_repo.upsert_accrued_income_offset_state.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()


async def test_consumer_uses_trade_fee_in_calculation(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_buy_kafka_message: MagicMock,
    mock_dependencies,
):
    """
    GIVEN a new BUY transaction message with a trade_fee
    WHEN the consumer processes it using the real engine
    THEN the final updated transaction should have a net_cost that includes the fee.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None
    mock_repo.update_transaction_costs.side_effect = lambda arg: arg

    # ACT
    await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    # ASSERT
    mock_repo.update_transaction_costs.assert_called_once()
    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]

    assert updated_transaction_arg.net_cost == Decimal("1507.50")
    assert updated_transaction_arg.realized_gain_loss == Decimal("0")
    assert updated_transaction_arg.realized_gain_loss_local == Decimal("0")
    mock_repo.upsert_buy_lot_state.assert_called_once()
    mock_repo.upsert_accrued_income_offset_state.assert_called_once()


async def test_consumer_uses_fee_breakdown_when_provided(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_buy_kafka_message: MagicMock,
    mock_dependencies,
):
    """
    GIVEN a BUY event with explicit fee breakdown fields
    WHEN the consumer transforms and processes the event
    THEN fee components should be used (not only trade_fee),
    and total trade_fee should match component sum.
    """
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    incoming_event_dict = json.loads(mock_buy_kafka_message.value().decode("utf-8"))
    incoming_event_dict["trade_fee"] = "0.00"
    incoming_event_dict["brokerage"] = "2.50"
    incoming_event_dict["stamp_duty"] = "1.20"
    incoming_event_dict["exchange_fee"] = "0.70"
    incoming_event_dict["gst"] = "0.45"
    incoming_event_dict["other_fees"] = "0.15"
    mock_buy_kafka_message.value.return_value = json.dumps(incoming_event_dict).encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None
    mock_repo.update_transaction_costs.side_effect = lambda arg: arg

    await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]
    assert updated_transaction_arg.fees.brokerage == Decimal("2.50")
    assert updated_transaction_arg.fees.stamp_duty == Decimal("1.20")
    assert updated_transaction_arg.fees.exchange_fee == Decimal("0.70")
    assert updated_transaction_arg.fees.gst == Decimal("0.45")
    assert updated_transaction_arg.fees.other_fees == Decimal("0.15")
    assert updated_transaction_arg.fees.total_fees == Decimal("5.00")


async def test_consumer_propagates_epoch_field(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_buy_kafka_message: MagicMock,
    mock_dependencies,
):
    """
    GIVEN an incoming transaction event with an epoch
    WHEN the consumer processes it
    THEN the outbound event it creates should also contain that same epoch.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    incoming_event_dict = mock_buy_kafka_message.value().decode("utf-8")
    incoming_event_dict = json.loads(incoming_event_dict)
    incoming_event_dict["epoch"] = 2
    mock_buy_kafka_message.value.return_value = json.dumps(incoming_event_dict).encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None

    exclude_fields = {
        "portfolio_base_currency",
        "fees",
        "accrued_interest",
        "epoch",
        "net_transaction_amount",
        "average_price",
        "error_reason",
    }
    mock_repo.update_transaction_costs.side_effect = lambda arg: DBTransaction(
        **arg.model_dump(exclude=exclude_fields)
    )

    # ACT
    await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    # ASSERT
    mock_outbox_repo.create_outbox_event.assert_called_once()
    outbound_payload = mock_outbox_repo.create_outbox_event.call_args.kwargs["payload"]
    assert outbound_payload["epoch"] == 2


async def test_consumer_retries_when_portfolio_not_found(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_buy_kafka_message: MagicMock,
    mock_dependencies,
):
    """
    GIVEN a transaction message
    WHEN the corresponding portfolio is not found on the first attempt
    THEN the consumer should raise PortfolioNotFoundError to trigger a retry.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_portfolio.return_value = None

    # ACT & ASSERT
    with pytest.raises(PortfolioNotFoundError):
        await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    mock_repo.get_portfolio.assert_awaited()
    assert mock_repo.get_portfolio.await_count > 0
    mock_repo.get_transaction_history.assert_not_called()


async def test_consumer_selects_avco_strategy_for_portfolio(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_buy_kafka_message: MagicMock,
    mock_dependencies,
):
    """
    GIVEN a portfolio configured with the 'AVCO' cost basis method
    WHEN the consumer processes a message for it
    THEN it should instantiate the AverageCostBasisStrategy.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    # This is the key part of the test: the portfolio has the AVCO method set.
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01", cost_basis_method="AVCO"
    )

    # We patch the strategy classes to act as spies, checking if they were instantiated.
    with (
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.FIFOBasisStrategy"
        ) as mock_fifo,
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.AverageCostBasisStrategy"
        ) as mock_avco,
    ):
        # ACT
        await cost_calculator_consumer.process_message(mock_buy_kafka_message)

        # ASSERT
        mock_avco.assert_called_once()
        mock_fifo.assert_not_called()


async def test_consumer_assigns_avco_sell_policy_metadata(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_sell_kafka_message: MagicMock,
    mock_dependencies,
):
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    buy_history = DBTransaction(
        transaction_id="BUY_AVCO_01",
        portfolio_id="PORT_COST_01",
        security_id="SEC_COST_01",
        instrument_id="AAPL",
        transaction_type="BUY",
        transaction_date=datetime(2025, 1, 10),
        quantity=Decimal("20"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("3000.0"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("3000"),
        net_cost_local=Decimal("3000"),
        transaction_fx_rate=Decimal("1.0"),
        trade_fee=Decimal("0.0"),
    )
    mock_repo.get_transaction_history.return_value = [buy_history]
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01", cost_basis_method="AVCO"
    )
    mock_repo.get_fx_rate.return_value = None
    mock_repo.update_transaction_costs.side_effect = lambda arg: arg

    await cost_calculator_consumer.process_message(mock_sell_kafka_message)

    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]
    assert updated_transaction_arg.calculation_policy_id == SELL_AVCO_POLICY_ID
    assert updated_transaction_arg.calculation_policy_version == SELL_DEFAULT_POLICY_VERSION


async def test_consumer_defer_when_fx_rate_missing(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_buy_kafka_message: MagicMock,
    mock_dependencies,
):
    """
    GIVEN a cross-currency BUY where FX is not yet available
    WHEN the consumer processes the message
    THEN it should raise RetryableConsumerError so BaseConsumer does not commit or DLQ it.
    """
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    incoming_event_dict = json.loads(mock_buy_kafka_message.value().decode("utf-8"))
    incoming_event_dict["trade_currency"] = "JPY"
    incoming_event_dict["currency"] = "JPY"
    incoming_event_dict["transaction_date"] = "2025-12-05T10:00:00Z"
    mock_buy_kafka_message.value.return_value = json.dumps(incoming_event_dict).encode("utf-8")

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="SGD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None

    with pytest.raises(RetryableConsumerError):
        await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    cost_calculator_consumer._send_to_dlq_async.assert_not_awaited()


async def test_consumer_emits_sell_lifecycle_metrics(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_sell_kafka_message: MagicMock,
    mock_dependencies,
):
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    buy_history = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        security_id="SEC_COST_01",
        instrument_id="AAPL",
        transaction_type="BUY",
        transaction_date=datetime(2025, 1, 10),
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("1500"),
        net_cost_local=Decimal("1500"),
        transaction_fx_rate=Decimal("1.0"),
        trade_fee=Decimal("0.0"),
    )
    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = [buy_history]
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None
    mock_repo.update_transaction_costs.side_effect = lambda arg: arg

    sell_counter = MagicMock()
    sell_counter.labels.return_value = MagicMock(inc=MagicMock())
    buy_counter = MagicMock()
    buy_counter.labels.return_value = MagicMock(inc=MagicMock())

    with (
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.SELL_LIFECYCLE_STAGE_TOTAL",
            sell_counter,
        ),
        patch(
            "src.services.calculators.cost_calculator_service.app.consumer.BUY_LIFECYCLE_STAGE_TOTAL",
            buy_counter,
        ),
    ):
        await cost_calculator_consumer.process_message(mock_sell_kafka_message)

    stage_calls = {(args[0], args[1]) for args, _ in sell_counter.labels.call_args_list}
    assert ("persist_transaction_costs", "attempt") in stage_calls
    assert ("persist_transaction_costs", "success") in stage_calls
    assert ("emit_outbox", "success") in stage_calls


async def test_consumer_assigns_dividend_metadata_defaults(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_dividend_kafka_message: MagicMock,
    mock_dependencies,
):
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None
    mock_repo.update_transaction_costs.side_effect = lambda arg: arg

    await cost_calculator_consumer.process_message(mock_dividend_kafka_message)

    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]
    assert (
        updated_transaction_arg.economic_event_id
        == "EVT-DIVIDEND-PORT_COST_01-DIV01"
    )
    assert (
        updated_transaction_arg.linked_transaction_group_id
        == "LTG-DIVIDEND-PORT_COST_01-DIV01"
    )
    assert updated_transaction_arg.calculation_policy_id == DIVIDEND_DEFAULT_POLICY_ID
    assert (
        updated_transaction_arg.calculation_policy_version
        == DIVIDEND_DEFAULT_POLICY_VERSION
    )

    payload = mock_outbox_repo.create_outbox_event.call_args.kwargs["payload"]
    assert payload["economic_event_id"] == "EVT-DIVIDEND-PORT_COST_01-DIV01"
    assert (
        payload["linked_transaction_group_id"] == "LTG-DIVIDEND-PORT_COST_01-DIV01"
    )


async def test_consumer_assigns_interest_metadata_defaults(
    cost_calculator_consumer: CostCalculatorConsumer,
    mock_interest_kafka_message: MagicMock,
    mock_dependencies,
):
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id="PORT_COST_01"
    )
    mock_repo.get_fx_rate.return_value = None
    mock_repo.update_transaction_costs.side_effect = lambda arg: arg

    await cost_calculator_consumer.process_message(mock_interest_kafka_message)

    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]
    assert updated_transaction_arg.economic_event_id == "EVT-INTEREST-PORT_COST_01-INT01"
    assert (
        updated_transaction_arg.linked_transaction_group_id
        == "LTG-INTEREST-PORT_COST_01-INT01"
    )
    assert updated_transaction_arg.calculation_policy_id == INTEREST_DEFAULT_POLICY_ID
    assert (
        updated_transaction_arg.calculation_policy_version
        == INTEREST_DEFAULT_POLICY_VERSION
    )

    payload = mock_outbox_repo.create_outbox_event.call_args.kwargs["payload"]
    assert payload["economic_event_id"] == "EVT-INTEREST-PORT_COST_01-INT01"
    assert payload["linked_transaction_group_id"] == "LTG-INTEREST-PORT_COST_01-INT01"
