from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from cost_engine.domain.enums.transaction_type import (
    TransactionType,
)
from cost_engine.domain.models.transaction import (
    Fees,
    Transaction,
)
from cost_engine.processing.cost_basis_strategies import (
    FIFOBasisStrategy,
)
from cost_engine.processing.cost_calculator import (
    CostCalculator,
)
from cost_engine.processing.disposition_engine import (
    DispositionEngine,
)
from cost_engine.processing.error_reporter import (
    ErrorReporter,
)


@pytest.fixture
def mock_disposition_engine():
    mock = MagicMock(spec=DispositionEngine)
    mock.get_available_quantity.return_value = Decimal("1000000")
    return mock


@pytest.fixture
def error_reporter():
    return ErrorReporter()


@pytest.fixture
def cost_calculator(mock_disposition_engine, error_reporter):
    return CostCalculator(disposition_engine=mock_disposition_engine, error_reporter=error_reporter)


@pytest.fixture
def buy_transaction():
    return Transaction(
        transaction_id="BUY001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.BUY,
        transaction_date=datetime(2023, 1, 1),
        settlement_date=datetime(2023, 1, 3),
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("1500"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("5.5")),
        accrued_interest=Decimal("10.0"),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )


@pytest.fixture
def sell_transaction():
    return Transaction(
        transaction_id="SELL001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.SELL,
        transaction_date=datetime(2023, 1, 10),
        settlement_date=datetime(2023, 1, 12),
        quantity=Decimal("5"),
        gross_transaction_amount=Decimal("800"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("3.0")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )


def test_buy_strategy(cost_calculator, mock_disposition_engine, buy_transaction):
    cost_calculator.calculate_transaction_costs(buy_transaction)
    assert buy_transaction.net_cost_local == Decimal("1515.5")
    assert buy_transaction.net_cost == Decimal("1515.5")
    assert buy_transaction.gross_cost == Decimal("1500")
    assert buy_transaction.realized_gain_loss == Decimal("0")
    assert buy_transaction.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(buy_transaction)


def test_buy_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    dual_currency_buy = Transaction(
        transaction_id="DC_BUY_01",
        portfolio_id="P_USD",
        instrument_id="AIR.lotus-performance",
        security_id="S_AIR",
        transaction_type=TransactionType.BUY,
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("15000"),
        trade_currency="EUR",
        fees=Fees(brokerage=Decimal("10")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.15"),
    )
    cost_calculator.calculate_transaction_costs(dual_currency_buy)
    assert dual_currency_buy.net_cost_local == Decimal("15010")
    assert dual_currency_buy.net_cost == Decimal("17261.50")
    assert dual_currency_buy.gross_cost == Decimal("17250.00")
    assert dual_currency_buy.realized_gain_loss == Decimal("0")
    assert dual_currency_buy.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(dual_currency_buy)


def test_buy_strategy_supports_policy_hook_for_accrued_interest_exclusion(
    cost_calculator, mock_disposition_engine
):
    bond_buy = Transaction(
        transaction_id="BOND_BUY_01",
        portfolio_id="P_USD",
        instrument_id="UST5Y",
        security_id="S_UST5Y",
        transaction_type=TransactionType.BUY,
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("98000"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("40")),
        accrued_interest=Decimal("1250"),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        calculation_policy_id="BUY_EXCLUDE_ACCRUED_INTEREST_FROM_BOOK_COST",
    )

    cost_calculator.calculate_transaction_costs(bond_buy)

    assert bond_buy.net_cost_local == Decimal("98040")
    assert bond_buy.net_cost == Decimal("98040")
    assert bond_buy.realized_gain_loss == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(bond_buy)


def test_buy_strategy_rejects_zero_quantity_with_invariant_error(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_buy = Transaction(
        transaction_id="BUY_ZERO_QTY",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.BUY,
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("0"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_buy)

    assert error_reporter.has_errors_for("BUY_ZERO_QTY")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_sell_strategy_gain(cost_calculator, mock_disposition_engine, sell_transaction):
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("500"),
        Decimal("500"),
        Decimal("5"),
        None,
    )
    cost_calculator.calculate_transaction_costs(sell_transaction)
    assert sell_transaction.realized_gain_loss == Decimal("297.0")
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(sell_transaction)


def test_sell_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    dual_currency_sell = Transaction(
        transaction_id="DC_SELL_01",
        portfolio_id="P_USD",
        instrument_id="AIR.lotus-performance",
        security_id="S_AIR",
        transaction_type=TransactionType.SELL,
        transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("50"),
        gross_transaction_amount=Decimal("8000"),
        trade_currency="EUR",
        fees=Fees(brokerage=Decimal("8")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.20"),
    )
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("8250"),
        Decimal("7500"),
        Decimal("50"),
        None,
    )
    cost_calculator.calculate_transaction_costs(dual_currency_sell)
    assert dual_currency_sell.realized_gain_loss_local == Decimal("492")
    assert dual_currency_sell.realized_gain_loss.quantize(Decimal("0.01")) == Decimal("1340.40")
    assert dual_currency_sell.net_cost == Decimal("-8250")
    assert dual_currency_sell.net_cost_local == Decimal("-7500")


def test_sell_strategy_rejects_negative_net_proceeds(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_sell = Transaction(
        transaction_id="SELL_NEG_PROCEEDS",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.SELL,
        transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("5"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("150")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_sell)

    assert error_reporter.has_errors_for("SELL_NEG_PROCEEDS")
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_rejects_non_positive_consumed_quantity(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("500"),
        Decimal("500"),
        Decimal("0"),
        None,
    )

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for("SELL001")


def test_sell_strategy_blocks_oversold_under_strict_policy(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    mock_disposition_engine.get_available_quantity.return_value = Decimal("3")

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for("SELL001")
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_reports_unsupported_oversold_policy(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    sell_transaction.calculation_policy_id = "SELL_ALLOW_OVERSOLD_POLICY"
    mock_disposition_engine.get_available_quantity.return_value = Decimal("3")

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for("SELL001")
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_multi_lot_fifo():
    error_reporter = ErrorReporter()
    fifo_strategy = FIFOBasisStrategy()
    disposition_engine = DispositionEngine(cost_basis_strategy=fifo_strategy)
    cost_calculator = CostCalculator(
        disposition_engine=disposition_engine, error_reporter=error_reporter
    )
    buy_txn_1 = Transaction(
        transaction_id="BUY001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(buy_txn_1)
    buy_txn_2 = Transaction(
        transaction_id="BUY002",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("50"),
        gross_transaction_amount=Decimal("600"),
        net_cost=Decimal("600"),
        net_cost_local=Decimal("600"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(buy_txn_2)
    sell_txn = Transaction(
        transaction_id="SELL001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="SELL",
        transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("120"),
        gross_transaction_amount=Decimal("1800"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(sell_txn)
    assert sell_txn.realized_gain_loss == Decimal("560")
    assert not error_reporter.has_errors()
    assert disposition_engine.get_available_quantity("P1", "AAPL") == Decimal("30")


def test_deposit_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    deposit_transaction = Transaction(
        transaction_id="DEPOSIT001",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type=TransactionType.DEPOSIT,
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("10000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(deposit_transaction)
    assert deposit_transaction.net_cost == Decimal("10000")
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert call_args.quantity == Decimal("10000")


def test_dividend_transaction_has_zero_cost(cost_calculator, mock_disposition_engine):
    dividend_transaction = Transaction(
        transaction_id="DIV001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.DIVIDEND,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("500.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(dividend_transaction)
    assert dividend_transaction.net_cost == Decimal("0")
    assert dividend_transaction.realized_gain_loss == Decimal("0")
    assert dividend_transaction.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_accepts_string_zero_price(
    cost_calculator, mock_disposition_engine, error_reporter
):
    dividend_transaction = Transaction(
        transaction_id="DIV_STR_PRICE_0",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.DIVIDEND,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price="0",
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(dividend_transaction)
    assert not error_reporter.has_errors_for("DIV_STR_PRICE_0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_rejects_non_zero_quantity(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_dividend = Transaction(
        transaction_id="DIV_BAD_QTY",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.DIVIDEND,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("1"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_dividend)
    assert error_reporter.has_errors_for("DIV_BAD_QTY")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_rejects_non_zero_price(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_dividend = Transaction(
        transaction_id="DIV_BAD_PRICE",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.DIVIDEND,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_dividend)
    assert error_reporter.has_errors_for("DIV_BAD_PRICE")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_rejects_non_positive_gross_amount(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_dividend = Transaction(
        transaction_id="DIV_BAD_GROSS",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.DIVIDEND,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_dividend)
    assert error_reporter.has_errors_for("DIV_BAD_GROSS")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_transaction_has_zero_cost_and_explicit_zero_realized_pnl(
    cost_calculator, mock_disposition_engine
):
    interest_transaction = Transaction(
        transaction_id="INT001",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type=TransactionType.INTEREST,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(interest_transaction)
    assert interest_transaction.net_cost == Decimal("0")
    assert interest_transaction.realized_gain_loss == Decimal("0")
    assert interest_transaction.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_rejects_non_zero_quantity(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_interest = Transaction(
        transaction_id="INT_BAD_QTY",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type=TransactionType.INTEREST,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("1"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_interest)
    assert error_reporter.has_errors_for("INT_BAD_QTY")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_rejects_non_zero_price(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_interest = Transaction(
        transaction_id="INT_BAD_PRICE",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type=TransactionType.INTEREST,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("5"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_interest)
    assert error_reporter.has_errors_for("INT_BAD_PRICE")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_rejects_non_positive_gross_amount(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_interest = Transaction(
        transaction_id="INT_BAD_GROSS",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type=TransactionType.INTEREST,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_interest)
    assert error_reporter.has_errors_for("INT_BAD_GROSS")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_allows_expense_direction_baseline(
    cost_calculator, mock_disposition_engine, error_reporter
):
    expense_interest = Transaction(
        transaction_id="INT_EXPENSE_OK",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type=TransactionType.INTEREST,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        interest_direction="EXPENSE",
    )

    cost_calculator.calculate_transaction_costs(expense_interest)
    assert not error_reporter.has_errors_for("INT_EXPENSE_OK")
    assert expense_interest.realized_gain_loss == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_rejects_unknown_direction(cost_calculator, error_reporter):
    invalid_direction = Transaction(
        transaction_id="INT_BAD_DIR",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type=TransactionType.INTEREST,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        interest_direction="UNKNOWN",
    )

    cost_calculator.calculate_transaction_costs(invalid_direction)
    assert error_reporter.has_errors_for("INT_BAD_DIR")


def test_transfer_in_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    transfer_in_transaction = Transaction(
        transaction_id="TRANSFER_IN_01",
        portfolio_id="P1",
        instrument_id="IBM",
        security_id="S_IBM",
        transaction_type="TRANSFER_IN",
        transaction_date=datetime(2023, 2, 1),
        quantity=Decimal("100"),
        price=Decimal("150"),
        gross_transaction_amount=Decimal("15000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(transfer_in_transaction)
    assert transfer_in_transaction.net_cost == Decimal("15000")
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert call_args.quantity == Decimal("100")
    assert call_args.net_cost == Decimal("15000")


def test_transfer_out_strategy_consumes_lot_without_pnl(cost_calculator, mock_disposition_engine):
    """
    Tests that a TRANSFER_OUT transaction consumes a cost lot but does not generate P&L.
    """
    # Arrange
    transfer_out_transaction = Transaction(
        transaction_id="TRANSFER_OUT_01",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="TRANSFER_OUT",
        transaction_date=datetime(2023, 2, 15),
        quantity=Decimal("20"),
        price=Decimal("160"),
        gross_transaction_amount=Decimal("3200"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    # Simulate the disposition engine returning the cost of the transferred shares
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("3000"),
        Decimal("3000"),
        Decimal("20"),
        None,
    )

    # Act
    cost_calculator.calculate_transaction_costs(transfer_out_transaction)

    # Assert
    # It should have called the disposition engine to "consume" the shares
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(transfer_out_transaction)

    # Crucially, it should NOT have calculated a realized gain/loss
    assert transfer_out_transaction.realized_gain_loss is None


# --- NEW FAILING TEST ---
def test_withdrawal_strategy_consumes_lot_without_pnl(cost_calculator, mock_disposition_engine):
    """
    Tests that a WITHDRAWAL transaction consumes a cash cost lot but does not generate P&L.
    This will fail with the current DefaultStrategy mapping.
    """
    # Arrange
    withdrawal_transaction = Transaction(
        transaction_id="WITHDRAWAL_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="WITHDRAWAL",
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("500"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    # Simulate the disposition engine returning the cost of the withdrawn cash
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("500"),
        Decimal("500"),
        Decimal("500"),
        None,
    )

    # Act
    cost_calculator.calculate_transaction_costs(withdrawal_transaction)

    # Assert
    # It should have called the disposition engine to "consume" the cash lot
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(withdrawal_transaction)

    # Crucially, it should NOT have calculated a realized gain/loss
    assert withdrawal_transaction.realized_gain_loss is None


def test_spin_off_basis_only_strategy_reduces_cost_without_lot_consumption(
    cost_calculator, mock_disposition_engine
):
    spin_off_transaction = Transaction(
        transaction_id="SPIN_OFF_01",
        portfolio_id="P1",
        instrument_id="SRC_SEC",
        security_id="SRC_SEC",
        transaction_type="SPIN_OFF",
        transaction_date=datetime(2023, 3, 1),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("2500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(spin_off_transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert spin_off_transaction.net_cost == Decimal("-2500")
    assert spin_off_transaction.net_cost_local == Decimal("-2500")
    assert spin_off_transaction.realized_gain_loss is None


def test_spin_in_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    spin_in_transaction = Transaction(
        transaction_id="SPIN_IN_01",
        portfolio_id="P1",
        instrument_id="NEW_SEC",
        security_id="NEW_SEC",
        transaction_type="SPIN_IN",
        transaction_date=datetime(2023, 3, 1),
        quantity=Decimal("20"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("2500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(spin_in_transaction)

    mock_disposition_engine.add_buy_lot.assert_called_once_with(spin_in_transaction)
    assert spin_in_transaction.net_cost == Decimal("2500")


@pytest.mark.parametrize(
    "transaction_type",
    [
        "SPLIT",
        "REVERSE_SPLIT",
        "CONSOLIDATION",
        "BONUS_ISSUE",
        "STOCK_DIVIDEND",
    ],
)
def test_same_instrument_ca_restatement_types_preserve_total_basis(
    cost_calculator, mock_disposition_engine, transaction_type
):
    txn = Transaction(
        transaction_id=f"{transaction_type}_01",
        portfolio_id="P1",
        instrument_id="EQ1",
        security_id="EQ1",
        transaction_type=transaction_type,
        transaction_date=datetime(2024, 1, 1),
        quantity=Decimal("10"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(txn)

    assert txn.net_cost == Decimal("0")
    assert txn.net_cost_local == Decimal("0")
    assert txn.gross_cost == Decimal("0")
    assert txn.realized_gain_loss == Decimal("0")
    assert txn.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_rights_delivery_and_allocate_use_inflow_strategy(cost_calculator, mock_disposition_engine):
    for tx_type in ("RIGHTS_ALLOCATE", "RIGHTS_SHARE_DELIVERY"):
        txn = Transaction(
            transaction_id=f"{tx_type}_01",
            portfolio_id="P1",
            instrument_id="RIGHTS_SEC",
            security_id="RIGHTS_SEC",
            transaction_type=tx_type,
            transaction_date=datetime(2024, 1, 1),
            quantity=Decimal("5"),
            price=Decimal("0"),
            gross_transaction_amount=Decimal("0"),
            trade_currency="USD",
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal("1.0"),
        )
        cost_calculator.calculate_transaction_costs(txn)
    assert mock_disposition_engine.add_buy_lot.call_count >= 2


def test_rights_outflow_types_consume_lots_without_realized_pnl(
    cost_calculator, mock_disposition_engine
):
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("100"),
        Decimal("100"),
        Decimal("1"),
        None,
    )
    for tx_type in ("RIGHTS_SUBSCRIBE", "RIGHTS_OVERSUBSCRIBE", "RIGHTS_SELL", "RIGHTS_EXPIRE"):
        txn = Transaction(
            transaction_id=f"{tx_type}_01",
            portfolio_id="P1",
            instrument_id="RIGHTS_SEC",
            security_id="RIGHTS_SEC",
            transaction_type=tx_type,
            transaction_date=datetime(2024, 1, 1),
            quantity=Decimal("1"),
            price=Decimal("0"),
            gross_transaction_amount=Decimal("0"),
            trade_currency="USD",
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal("1.0"),
        )
        cost_calculator.calculate_transaction_costs(txn)
        assert txn.realized_gain_loss is None
