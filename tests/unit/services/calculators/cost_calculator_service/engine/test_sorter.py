from datetime import datetime
from decimal import Decimal

import pytest
from cost_engine.domain.models.transaction import (
    Transaction,
)
from cost_engine.processing.sorter import (
    TransactionSorter,
)


@pytest.fixture
def sorter():
    return TransactionSorter()


def _transaction(
    *,
    transaction_id: str,
    transaction_date: datetime,
    quantity: Decimal = Decimal("1"),
    instrument_id: str = "A",
    security_id: str = "S1",
    transaction_type: str = "BUY",
    product_type: str | None = None,
    asset_class: str | None = None,
    component_type: str | None = None,
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        transaction_date=transaction_date,
        quantity=quantity,
        portfolio_id="P1",
        instrument_id=instrument_id,
        security_id=security_id,
        transaction_type=transaction_type,
        settlement_date=transaction_date,
        gross_transaction_amount=quantity,
        trade_currency="USD",
        portfolio_base_currency="USD",
        product_type=product_type,
        asset_class=asset_class,
        component_type=component_type,
    )


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


def test_sort_bundle_a_dependency_and_target_ordering(sorter):
    """
    Bundle A ordering should process source-out before target-in legs,
    and target-in legs should follow child_sequence_hint.
    """
    same_day = datetime(2026, 1, 10)
    target_2 = Transaction(
        transaction_id="t_target_2",
        transaction_date=same_day,
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="A",
        security_id="S1",
        transaction_type="DEMERGER_IN",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        child_sequence_hint=2,
        target_instrument_id="TGT2",
    )
    source = Transaction(
        transaction_id="t_source",
        transaction_date=same_day,
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="A",
        security_id="S1",
        transaction_type="DEMERGER_OUT",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    target_1 = Transaction(
        transaction_id="t_target_1",
        transaction_date=same_day,
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="A",
        security_id="S1",
        transaction_type="DEMERGER_IN",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        child_sequence_hint=1,
        target_instrument_id="TGT1",
    )

    sorted_list = sorter.sort_transactions([], [target_2, source, target_1])
    assert [t.transaction_id for t in sorted_list] == ["t_source", "t_target_1", "t_target_2"]


def test_sort_rights_lifecycle_dependency_ordering(sorter):
    same_day = datetime(2026, 1, 10)
    allocate = Transaction(
        transaction_id="t_allocate",
        transaction_date=same_day,
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="RIGHTS_SEC",
        security_id="RIGHTS_SEC",
        transaction_type="RIGHTS_ALLOCATE",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    subscribe = Transaction(
        transaction_id="t_subscribe",
        transaction_date=same_day,
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="RIGHTS_SEC",
        security_id="RIGHTS_SEC",
        transaction_type="RIGHTS_SUBSCRIBE",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    delivery = Transaction(
        transaction_id="t_delivery",
        transaction_date=same_day,
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="NEW_SEC",
        security_id="NEW_SEC",
        transaction_type="RIGHTS_SHARE_DELIVERY",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    refund = Transaction(
        transaction_id="t_refund",
        transaction_date=same_day,
        quantity=Decimal("1"),
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="RIGHTS_REFUND",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )

    sorted_list = sorter.sort_transactions([], [refund, delivery, subscribe, allocate])
    assert [t.transaction_id for t in sorted_list] == [
        "t_allocate",
        "t_subscribe",
        "t_delivery",
        "t_refund",
    ]


def test_sort_cash_inflow_before_cash_outflow_on_same_timestamp(sorter):
    same_day = datetime(2025, 8, 28)
    deposit = Transaction(
        transaction_id="TS_DEP_01",
        transaction_date=same_day,
        quantity=Decimal("5500"),
        portfolio_id="P1",
        instrument_id="CASH",
        security_id="CASH",
        transaction_type="DEPOSIT",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("5500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        product_type="Cash",
        asset_class="Cash",
    )
    settlement_sell = Transaction(
        transaction_id="TS_CASH_SETTLE_BUY_01",
        transaction_date=same_day,
        quantity=Decimal("5500"),
        portfolio_id="P1",
        instrument_id="CASH",
        security_id="CASH",
        transaction_type="SELL",
        settlement_date=same_day,
        gross_transaction_amount=Decimal("5500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        product_type="Cash",
        asset_class="Cash",
    )

    sorted_list = sorter.sort_transactions([], [settlement_sell, deposit])
    assert [t.transaction_id for t in sorted_list] == ["TS_DEP_01", "TS_CASH_SETTLE_BUY_01"]


def test_sort_bundle_dependency_normalizes_transaction_type(sorter):
    same_day = datetime(2026, 1, 10)
    target = _transaction(
        transaction_id="t_target",
        transaction_date=same_day,
        quantity=Decimal("10"),
        transaction_type=" demerger_in ",
    )
    source = _transaction(
        transaction_id="t_source",
        transaction_date=same_day,
        quantity=Decimal("1"),
        transaction_type=" demerger_out ",
    )

    sorted_list = sorter.sort_transactions([], [target, source])
    assert [t.transaction_id for t in sorted_list] == ["t_source", "t_target"]


def test_sort_cash_dependencies_normalize_source_vocabulary(sorter):
    same_day = datetime(2025, 8, 28)
    fee = _transaction(
        transaction_id="t_fee",
        transaction_date=same_day,
        quantity=Decimal("5000"),
        instrument_id=" cash_usd ",
        security_id=" cash_usd ",
        transaction_type=" fee ",
        product_type=" cash ",
        asset_class=" cash ",
    )
    deposit = _transaction(
        transaction_id="t_deposit",
        transaction_date=same_day,
        quantity=Decimal("1"),
        instrument_id=" cash_usd ",
        security_id=" cash_usd ",
        transaction_type=" deposit ",
        product_type=" cash ",
        asset_class=" cash ",
    )

    sorted_list = sorter.sort_transactions([], [fee, deposit])
    assert [t.transaction_id for t in sorted_list] == ["t_deposit", "t_fee"]


def test_sort_cash_settlement_component_types_bound_same_timestamp(sorter):
    same_day = datetime(2025, 8, 28)
    settlement_sell = _transaction(
        transaction_id="t_settlement_sell",
        transaction_date=same_day,
        quantity=Decimal("1000"),
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="CASH_MOVEMENT",
        product_type="Cash",
        asset_class="Cash",
        component_type="FX_CASH_SETTLEMENT_SELL",
    )
    neutral_cash = _transaction(
        transaction_id="t_neutral",
        transaction_date=same_day,
        quantity=Decimal("500"),
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="CASH_MOVEMENT",
        product_type="Cash",
        asset_class="Cash",
    )
    settlement_buy = _transaction(
        transaction_id="t_settlement_buy",
        transaction_date=same_day,
        quantity=Decimal("1"),
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="CASH_MOVEMENT",
        product_type="Cash",
        asset_class="Cash",
        component_type="FX_CASH_SETTLEMENT_BUY",
    )

    sorted_list = sorter.sort_transactions([], [settlement_sell, neutral_cash, settlement_buy])
    assert [t.transaction_id for t in sorted_list] == [
        "t_settlement_buy",
        "t_neutral",
        "t_settlement_sell",
    ]
