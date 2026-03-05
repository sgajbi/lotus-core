# tests/unit/libs/financial-calculator-engine/unit/test_sorter.py

from datetime import datetime
from decimal import Decimal

import pytest
from core.models.transaction import Transaction
from logic.sorter import TransactionSorter


@pytest.fixture
def sorter():
    return TransactionSorter()


def test_sort_by_date(sorter):
    # Arrange
    t1 = Transaction(
        transaction_id="t1",
        transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="A",
        security_id="S1",
        transaction_type="BUY",
        settlement_date=datetime(2023, 1, 5),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    t2 = Transaction(
        transaction_id="t2",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="A",
        security_id="S1",
        transaction_type="BUY",
        settlement_date=datetime(2023, 1, 1),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )

    # Act
    sorted_list = sorter.sort_transactions([], [t1, t2])

    # Assert
    assert [t.transaction_id for t in sorted_list] == ["t2", "t1"]


def test_sort_by_quantity_on_same_day(sorter):
    """
    Tests that for transactions on the same date, the one with the larger
    quantity comes first (descending order).
    """
    # Arrange
    same_day = datetime(2023, 1, 10)
    t_small_qty = Transaction(
        transaction_id="t_small",
        transaction_date=same_day,
        quantity=Decimal("50"),
        portfolio_id="P1",
        instrument_id="A",
        security_id="S1",
        transaction_type="BUY",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("50"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    t_large_qty = Transaction(
        transaction_id="t_large",
        transaction_date=same_day,
        quantity=Decimal("100"),
        portfolio_id="P1",
        instrument_id="A",
        security_id="S1",
        transaction_type="BUY",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )

    # Act
    # The initial order is small then large
    sorted_list = sorter.sort_transactions([], [t_small_qty, t_large_qty])

    # Assert
    # The final order should be large then small
    assert [t.transaction_id for t in sorted_list] == ["t_large", "t_small"]
