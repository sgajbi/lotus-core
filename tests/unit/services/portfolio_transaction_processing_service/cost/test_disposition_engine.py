from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisStrategy,
    CostBasisTransaction,
    LotDispositionEngine,
)


class _StringCountedAmount:
    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


@pytest.fixture
def mock_strategy() -> MagicMock:
    """Provides a mock of the CostBasisStrategy for testing the engine's delegation."""
    return MagicMock(spec=CostBasisStrategy)


@pytest.fixture
def disposition_engine(mock_strategy: MagicMock) -> LotDispositionEngine:
    """Provides a LotDispositionEngine instance initialized with the mock strategy."""
    return LotDispositionEngine(cost_basis_strategy=mock_strategy)


@pytest.fixture
def sample_transaction() -> CostBasisTransaction:
    """Provides a sample transaction for testing."""
    return CostBasisTransaction(
        transaction_id="TXN1",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        net_cost=Decimal("105"),
        net_cost_local=Decimal("105"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )


def test_add_buy_lot_delegates_to_strategy(
    disposition_engine: LotDispositionEngine,
    mock_strategy: MagicMock,
    sample_transaction: CostBasisTransaction,
):
    """
    Tests that add_buy_lot correctly calls the underlying strategy.
    """
    # Act
    disposition_engine.add_buy_lot(sample_transaction)

    # Assert
    mock_strategy.add_buy_lot.assert_called_once_with(sample_transaction)


def test_add_buy_lot_ignores_zero_quantity(
    disposition_engine: LotDispositionEngine,
    mock_strategy: MagicMock,
    sample_transaction: CostBasisTransaction,
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
    disposition_engine: LotDispositionEngine,
    mock_strategy: MagicMock,
    sample_transaction: CostBasisTransaction,
):
    """
    Tests that consume_sell_quantity correctly calls and returns values from the strategy.
    """
    # Arrange
    sample_transaction.transaction_type = "SELL"
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


def test_consume_sell_quantity_normalizes_quantity_once(
    disposition_engine: LotDispositionEngine,
    mock_strategy: MagicMock,
    sample_transaction: CostBasisTransaction,
):
    quantity = _StringCountedAmount("10")
    sample_transaction.transaction_type = "SELL"
    sample_transaction.quantity = quantity
    mock_strategy.consume_sell_quantity.return_value = (
        Decimal("105"),
        Decimal("105"),
        Decimal("10"),
        None,
    )

    result = disposition_engine.consume_sell_quantity(sample_transaction)

    mock_strategy.consume_sell_quantity.assert_called_once_with(
        sample_transaction.portfolio_id,
        sample_transaction.instrument_id,
        Decimal("10"),
    )
    assert quantity.string_call_count == 1
    assert result == (Decimal("105"), Decimal("105"), Decimal("10"), None)


def test_set_initial_lots_delegates_to_strategy(
    disposition_engine: LotDispositionEngine,
    mock_strategy: MagicMock,
    sample_transaction: CostBasisTransaction,
):
    """
    Tests that set_initial_lots correctly calls the underlying strategy with only BUY transactions.
    """
    # Arrange
    sell_transaction = sample_transaction.model_copy()
    sell_transaction.transaction_type = "SELL"
    transactions = [sample_transaction, sell_transaction]

    # Act
    disposition_engine.set_initial_lots(transactions)

    # Assert
    # It should have been called only with the list containing the buy transaction
    mock_strategy.set_initial_lots.assert_called_once_with([sample_transaction])


def test_set_initial_lots_normalizes_buy_transaction_type(
    disposition_engine: LotDispositionEngine,
    mock_strategy: MagicMock,
    sample_transaction: CostBasisTransaction,
):
    padded_buy = sample_transaction.model_copy(update={"transaction_type": " buy "})
    sell_transaction = sample_transaction.model_copy(update={"transaction_type": " sell "})

    disposition_engine.set_initial_lots([sell_transaction, padded_buy])

    mock_strategy.set_initial_lots.assert_called_once_with([padded_buy])


def test_restore_open_lots_preserves_non_buy_source_semantics(
    disposition_engine: LotDispositionEngine,
    mock_strategy,
    sample_transaction: CostBasisTransaction,
) -> None:
    transfer_in = sample_transaction.model_copy(update={"transaction_type": "TRANSFER_IN"})

    disposition_engine.restore_open_lots([transfer_in])

    mock_strategy.restore_open_lots.assert_called_once_with([transfer_in])
