# tests/unit/libs/financial-calculator-engine/unit/test_disposition_engine.py

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from core.enums.transaction_type import TransactionType
from core.models.transaction import Transaction
from logic.cost_basis_strategies import CostBasisStrategy
from logic.disposition_engine import DispositionEngine


@pytest.fixture
def mock_strategy() -> MagicMock:
    """Provides a mock of the CostBasisStrategy for testing the engine's delegation."""
    return MagicMock(spec=CostBasisStrategy)


@pytest.fixture
def disposition_engine(mock_strategy: MagicMock) -> DispositionEngine:
    """Provides a DispositionEngine instance initialized with the mock strategy."""
    return DispositionEngine(cost_basis_strategy=mock_strategy)


@pytest.fixture
def sample_transaction() -> Transaction:
    """Provides a sample transaction for testing."""
    return Transaction(
        transaction_id="TXN1",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type=TransactionType.BUY,
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        net_cost=Decimal("105"),
        net_cost_local=Decimal("105"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )


def test_add_buy_lot_delegates_to_strategy(
    disposition_engine: DispositionEngine, mock_strategy: MagicMock, sample_transaction: Transaction
):
    """
    Tests that add_buy_lot correctly calls the underlying strategy.
    """
    # Act
    disposition_engine.add_buy_lot(sample_transaction)

    # Assert
    mock_strategy.add_buy_lot.assert_called_once_with(sample_transaction)


def test_add_buy_lot_ignores_zero_quantity(
    disposition_engine: DispositionEngine, mock_strategy: MagicMock, sample_transaction: Transaction
):
    """
    Tests that a transaction with zero quantity is not added as a lot.
    """
    # Arrange
    sample_transaction.quantity = Decimal(0)

    # Act
    disposition_engine.add_buy_lot(sample_transaction)

    # Assert
    mock_strategy.add_buy_lot.assert_not_called()


def test_consume_sell_quantity_delegates_to_strategy(
    disposition_engine: DispositionEngine, mock_strategy: MagicMock, sample_transaction: Transaction
):
    """
    Tests that consume_sell_quantity correctly calls and returns values from the strategy.
    """
    # Arrange
    sample_transaction.transaction_type = TransactionType.SELL
    mock_strategy.consume_sell_quantity.return_value = (
        Decimal("105"),
        Decimal("105"),
        Decimal("10"),
        None,
    )

    # Act
    result = disposition_engine.consume_sell_quantity(sample_transaction)

    # Assert
    mock_strategy.consume_sell_quantity.assert_called_once_with(
        sample_transaction.portfolio_id,
        sample_transaction.instrument_id,
        sample_transaction.quantity,
    )
    assert result == (Decimal("105"), Decimal("105"), Decimal("10"), None)


def test_set_initial_lots_delegates_to_strategy(
    disposition_engine: DispositionEngine, mock_strategy: MagicMock, sample_transaction: Transaction
):
    """
    Tests that set_initial_lots correctly calls the underlying strategy with only BUY transactions.
    """
    # Arrange
    sell_transaction = sample_transaction.model_copy()
    sell_transaction.transaction_type = TransactionType.SELL
    transactions = [sample_transaction, sell_transaction]

    # Act
    disposition_engine.set_initial_lots(transactions)

    # Assert
    # It should have been called only with the list containing the buy transaction
    mock_strategy.set_initial_lots.assert_called_once_with([sample_transaction])
