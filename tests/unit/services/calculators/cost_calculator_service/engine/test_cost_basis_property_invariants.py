from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from cost_engine.domain.models.transaction import (
    Transaction,
)
from cost_engine.processing.cost_basis_strategies import (
    AverageCostBasisStrategy,
    FIFOBasisStrategy,
)
from hypothesis import given, settings
from hypothesis import strategies as st


def _buy_txn(transaction_id: str, quantity: Decimal, cost_per_share: Decimal) -> Transaction:
    total_cost = quantity * cost_per_share
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id="P_PROP",
        instrument_id="I_PROP",
        security_id="S_PROP",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1),
        quantity=quantity,
        gross_transaction_amount=total_cost,
        net_cost=total_cost,
        net_cost_local=total_cost,
        trade_currency="USD",
        portfolio_base_currency="USD",
    )


@settings(max_examples=75, deadline=None)
@given(
    lot_quantities=st.lists(
        st.integers(min_value=1, max_value=1000),
        min_size=1,
        max_size=8,
    ),
    sell_ratio_bps=st.integers(min_value=0, max_value=10000),
)
def test_fifo_quantity_conservation_invariant(lot_quantities: list[int], sell_ratio_bps: int):
    strategy = FIFOBasisStrategy()

    total_qty = Decimal(sum(lot_quantities))
    for idx, qty in enumerate(lot_quantities, start=1):
        strategy.add_buy_lot(
            _buy_txn(
                transaction_id=f"FIFO_BUY_{idx}",
                quantity=Decimal(qty),
                cost_per_share=Decimal("10"),
            )
        )

    sell_qty = (total_qty * Decimal(sell_ratio_bps) / Decimal(10000)).quantize(Decimal("1"))
    cogs_base, cogs_local, consumed_qty, error = strategy.consume_sell_quantity(
        portfolio_id="P_PROP",
        instrument_id="I_PROP",
        sell_quantity=sell_qty,
    )

    assert error is None
    assert consumed_qty == sell_qty
    assert cogs_base == cogs_local
    assert strategy.get_available_quantity("P_PROP", "I_PROP") == total_qty - sell_qty


@settings(max_examples=75, deadline=None)
@given(
    buy_qty_1=st.integers(min_value=1, max_value=500),
    buy_qty_2=st.integers(min_value=1, max_value=500),
    cost_ps_1=st.integers(min_value=1, max_value=100),
    cost_ps_2=st.integers(min_value=1, max_value=100),
    sell_qty_seed=st.integers(min_value=1, max_value=500),
    split_ratio_bps=st.integers(min_value=0, max_value=10000),
)
def test_avco_sequential_vs_combined_sell_cost_invariant(
    buy_qty_1: int,
    buy_qty_2: int,
    cost_ps_1: int,
    cost_ps_2: int,
    sell_qty_seed: int,
    split_ratio_bps: int,
):
    total_buy_qty = buy_qty_1 + buy_qty_2
    total_sell_qty = min(sell_qty_seed, total_buy_qty)
    first_sell_qty = int(total_sell_qty * split_ratio_bps / 10000)
    second_sell_qty = total_sell_qty - first_sell_qty

    sequential = AverageCostBasisStrategy()
    combined = AverageCostBasisStrategy()

    buy_1 = _buy_txn("AVCO_BUY_1", Decimal(buy_qty_1), Decimal(cost_ps_1))
    buy_2 = _buy_txn("AVCO_BUY_2", Decimal(buy_qty_2), Decimal(cost_ps_2))

    sequential.add_buy_lot(buy_1)
    sequential.add_buy_lot(buy_2)
    combined.add_buy_lot(buy_1)
    combined.add_buy_lot(buy_2)

    seq_cost_1, _, _, seq_error_1 = sequential.consume_sell_quantity(
        "P_PROP", "I_PROP", Decimal(first_sell_qty)
    )
    if second_sell_qty > 0:
        seq_cost_2, _, _, seq_error_2 = sequential.consume_sell_quantity(
            "P_PROP", "I_PROP", Decimal(second_sell_qty)
        )
    else:
        seq_cost_2, seq_error_2 = Decimal(0), None
    combined_cost, _, _, combined_error = combined.consume_sell_quantity(
        "P_PROP", "I_PROP", Decimal(total_sell_qty)
    )

    assert seq_error_1 is None
    assert seq_error_2 is None
    assert combined_error is None
    assert abs((seq_cost_1 + seq_cost_2) - combined_cost) <= Decimal("0.0000000000000000000001")
    assert sequential.get_available_quantity("P_PROP", "I_PROP") == combined.get_available_quantity(
        "P_PROP", "I_PROP"
    )
