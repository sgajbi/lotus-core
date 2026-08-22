"""Verify domain-owned FIFO and average-cost strategy behavior."""

from collections import deque
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostBasisStrategy,
    CostBasisTransaction,
    FIFOBasisStrategy,
    LotRestatementError,
    OpenLotState,
)

# --- Tests for AverageCostBasisStrategy ---


class _StringCountedAmount:
    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


@pytest.fixture
def avco_strategy():
    """Provides a clean instance of the AverageCostBasisStrategy."""
    return AverageCostBasisStrategy()


def _open_quantities(strategy) -> dict[str, Decimal]:
    return {
        transaction_id: state.quantity
        for transaction_id, state in strategy.get_open_lot_states().items()
    }


def _restatement_buy(
    *,
    transaction_id: str,
    quantity: str,
    cost: str,
) -> CostBasisTransaction:
    return CostBasisTransaction(
        transaction_id=transaction_id,
        portfolio_id="P-RESTATE",
        instrument_id="I-RESTATE",
        security_id="S-RESTATE",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1),
        quantity=Decimal(quantity),
        gross_transaction_amount=Decimal(cost),
        net_cost=Decimal(cost),
        net_cost_local=Decimal(cost),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )


@pytest.mark.parametrize("strategy_type", [FIFOBasisStrategy, AverageCostBasisStrategy])
def test_restored_buy_requires_original_quantity_authority(strategy_type) -> None:
    strategy = strategy_type()
    restored = _restatement_buy(
        transaction_id="BUY-RESTORED-MISSING-AUTHORITY",
        quantity="75",
        cost="750",
    ).model_copy(update={"source_lot_order_quantity": Decimal("100")})

    with pytest.raises(
        ValueError,
        match="Restored source lot is missing original quantity authority",
    ):
        strategy.add_buy_lot(restored)

    assert strategy.get_open_lot_states() == {}


@pytest.mark.parametrize("strategy_type", [FIFOBasisStrategy, AverageCostBasisStrategy])
def test_partial_disposal_then_split_restates_original_and_open_quantity_without_moving_basis(
    strategy_type,
) -> None:
    strategy = strategy_type()
    strategy.add_buy_lot(
        _restatement_buy(transaction_id="BUY-RESTATE", quantity="100", cost="1000")
    )
    disposed = strategy.consume_sell_quantity_with_allocations(
        "P-RESTATE",
        "I-RESTATE",
        Decimal("25"),
    )
    assert (disposed.cost_base, disposed.cost_local, disposed.consumed_quantity) == (
        Decimal("250"),
        Decimal("250"),
        Decimal("25"),
    )

    restatement = strategy.restate_lot_quantities(
        "P-RESTATE",
        "I-RESTATE",
        Decimal("75"),
    )

    state = strategy.get_open_lot_states()["BUY-RESTATE"]
    assert restatement.lineage_payload()["quantity_after"] == Decimal("150")
    assert (state.original_quantity, state.quantity, state.cost_local, state.cost_base) == (
        Decimal("200.0000000000"),
        Decimal("150.0000000000"),
        Decimal("750"),
        Decimal("750"),
    )
    final_disposal = strategy.consume_sell_quantity_with_allocations(
        "P-RESTATE",
        "I-RESTATE",
        Decimal("150"),
    )
    assert (final_disposal.cost_base, final_disposal.cost_local) == (
        Decimal("750"),
        Decimal("750"),
    )
    assert strategy.get_available_quantity("P-RESTATE", "I-RESTATE") == Decimal(0)


@pytest.mark.parametrize("strategy_type", [FIFOBasisStrategy, AverageCostBasisStrategy])
def test_reverse_split_restates_full_lot_and_conserves_basis(strategy_type) -> None:
    strategy = strategy_type()
    strategy.add_buy_lot(
        _restatement_buy(transaction_id="BUY-REVERSE", quantity="100", cost="1000")
    )

    strategy.restate_lot_quantities("P-RESTATE", "I-RESTATE", Decimal("-50"))

    state = strategy.get_open_lot_states()["BUY-REVERSE"]
    assert (state.original_quantity, state.quantity, state.cost_base) == (
        Decimal("50.0000000000"),
        Decimal("50.0000000000"),
        Decimal("1000"),
    )
    disposal = strategy.consume_sell_quantity_with_allocations(
        "P-RESTATE", "I-RESTATE", Decimal("50")
    )
    assert disposal.cost_base == Decimal("1000")


@pytest.mark.parametrize("strategy_type", [FIFOBasisStrategy, AverageCostBasisStrategy])
def test_nonrepresentable_restatement_fails_before_mutating_any_source(strategy_type) -> None:
    strategy = strategy_type()
    for index in range(3):
        strategy.add_buy_lot(
            _restatement_buy(
                transaction_id=f"BUY-NONREP-{index}",
                quantity="1",
                cost="10",
            )
        )
    states_before = strategy.get_open_lot_states()

    with pytest.raises(LotRestatementError, match="cannot be restated exactly"):
        strategy.restate_lot_quantities("P-RESTATE", "I-RESTATE", Decimal("1"))

    assert strategy.get_open_lot_states() == states_before
    assert strategy.get_available_quantity("P-RESTATE", "I-RESTATE") == Decimal("3")


def test_average_cost_nonrepresentable_segment_restatement_fails_before_mutation() -> None:
    strategy = AverageCostBasisStrategy()
    strategy.add_buy_lot(
        _restatement_buy(
            transaction_id="BUY-NONREP-SEGMENT",
            quantity="2",
            cost="20",
        )
    )
    strategy.consume_sell_quantity_with_allocations(
        "P-RESTATE",
        "I-RESTATE",
        Decimal("0.5"),
    )
    assert (
        strategy.transfer_basis_out(
            "P-RESTATE",
            "I-RESTATE",
            Decimal("1"),
            Decimal("1"),
        )
        is None
    )
    strategy.consume_sell_quantity_with_allocations(
        "P-RESTATE",
        "I-RESTATE",
        Decimal("0.5"),
    )
    states_before = strategy.get_open_lot_states()

    with pytest.raises(LotRestatementError, match="cannot be restated exactly"):
        strategy.restate_lot_quantities(
            "P-RESTATE",
            "I-RESTATE",
            Decimal("-0.6666666667"),
        )

    assert strategy.get_open_lot_states() == states_before
    assert strategy.get_available_quantity("P-RESTATE", "I-RESTATE") == Decimal("1.0")


@pytest.mark.parametrize("strategy_type", [FIFOBasisStrategy, AverageCostBasisStrategy])
def test_repeating_restatement_ratio_conserves_exact_base_and_local_basis(strategy_type) -> None:
    strategy = strategy_type()
    strategy.add_buy_lot(
        _restatement_buy(transaction_id="BUY-REPEATING", quantity="3", cost="1000")
    )
    before = strategy.get_open_lot_states()

    strategy.restate_lot_quantities("P-RESTATE", "I-RESTATE", Decimal("1"))

    after = strategy.get_open_lot_states()
    assert sum(state.cost_local for state in after.values()) == sum(
        state.cost_local for state in before.values()
    )
    assert sum(state.cost_base for state in after.values()) == sum(
        state.cost_base for state in before.values()
    )
    assert after["BUY-REPEATING"].quantity == Decimal("4.0000000000")


def test_average_cost_simple_disposition(avco_strategy: AverageCostBasisStrategy):
    """
    Tests a standard scenario for the Average Cost method.
    Scenario:
    1. Buy 100 shares for a total net cost of $1000.
    2. Buy 100 shares for a total net cost of $1200.
    - Total position: 200 shares, total cost: $2200, average cost: $11/share.
    3. Sell 50 shares.
    """
    # Arrange: Create the two buy transactions
    buy_txn_1 = CostBasisTransaction(
        transaction_id="BUY001",
        portfolio_id="P1",
        instrument_id="AVCO_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost_local=Decimal("1000"),
    )
    buy_txn_2 = CostBasisTransaction(
        transaction_id="BUY002",
        portfolio_id="P1",
        instrument_id="AVCO_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1200"),
        net_cost=Decimal("1200"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost_local=Decimal("1200"),
    )

    # Act: Add the buy lots to the strategy
    avco_strategy.add_buy_lot(buy_txn_1)
    avco_strategy.add_buy_lot(buy_txn_2)

    # Assert initial state
    assert avco_strategy.get_available_quantity("P1", "AVCO_STOCK") == Decimal("200")

    # Act: Consume a partial sell
    sell_quantity = Decimal("50")
    total_matched_cost_base, total_matched_cost_local, consumed_quantity, error = (
        avco_strategy.consume_sell_quantity(
            portfolio_id="P1", instrument_id="AVCO_STOCK", sell_quantity=sell_quantity
        )
    )

    # Assert the results of the disposition
    # Expected cost of goods sold = 50 shares * $11 avg_cost = $550
    assert total_matched_cost_base == Decimal("550")
    assert consumed_quantity == sell_quantity
    assert error is None
    assert _open_quantities(avco_strategy) == {
        "BUY001": Decimal("75"),
        "BUY002": Decimal("75"),
    }
    open_states = avco_strategy.get_open_lot_states()
    assert open_states["BUY001"].cost_base == Decimal("750")
    assert open_states["BUY002"].cost_base == Decimal("900")
    assert sum(state.cost_base for state in open_states.values()) == Decimal("1650")

    # Assert the final state
    assert avco_strategy.get_available_quantity("P1", "AVCO_STOCK") == Decimal("150")


def test_average_cost_dual_currency(avco_strategy: AverageCostBasisStrategy):
    """
    Tests AVCO with a USD portfolio trading a EUR stock with changing FX rates.
    """
    # ARRANGE
    # Buy 1: 100 shares @ €10/share, FX=1.10. Cost: €1000 local, $1100 base.
    buy1 = CostBasisTransaction(
        transaction_id="AVCO_BUY_1",
        portfolio_id="P_USD",
        instrument_id="EUR_STOCK",
        security_id="S_EUR",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        net_cost=Decimal("1100"),
        trade_currency="EUR",
        portfolio_base_currency="USD",
    )
    # Buy 2: 100 shares @ €12/share, FX=1.15. Cost: €1200 local, $1380 base.
    buy2 = CostBasisTransaction(
        transaction_id="AVCO_BUY_2",
        portfolio_id="P_USD",
        instrument_id="EUR_STOCK",
        security_id="S_EUR",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1200"),
        net_cost_local=Decimal("1200"),
        net_cost=Decimal("1380"),
        trade_currency="EUR",
        portfolio_base_currency="USD",
    )

    avco_strategy.add_buy_lot(buy1)
    avco_strategy.add_buy_lot(buy2)

    # State after buys: 200 shares, €2200 local cost, $2480 base cost.
    # Avg Cost: €11.00 local, $12.40 base.
    assert avco_strategy.get_available_quantity("P_USD", "EUR_STOCK") == Decimal("200")

    # ACT: Sell 50 shares
    cogs_base, cogs_local, consumed_qty, error = avco_strategy.consume_sell_quantity(
        portfolio_id="P_USD", instrument_id="EUR_STOCK", sell_quantity=Decimal("50")
    )

    # ASSERT
    assert error is None
    assert consumed_qty == Decimal("50")
    # COGS Local: 50 * €11.00 = €550
    assert cogs_local == pytest.approx(Decimal("550"))
    # COGS Base: 50 * $12.40 = $620
    assert cogs_base == pytest.approx(Decimal("620"))

    # Assert final state
    final_qty = avco_strategy.get_available_quantity("P_USD", "EUR_STOCK")
    assert final_qty == Decimal("150")
    assert _open_quantities(avco_strategy) == {
        "AVCO_BUY_1": Decimal("75"),
        "AVCO_BUY_2": Decimal("75"),
    }


def test_average_cost_disposition_exposes_source_contribution_deltas(
    avco_strategy: AverageCostBasisStrategy,
) -> None:
    buys = (
        CostBasisTransaction(
            transaction_id="AVCO_ALLOC_BUY_1",
            portfolio_id="P_USD",
            instrument_id="EUR_ALLOC_STOCK",
            security_id="S_EUR",
            transaction_type="BUY",
            transaction_date=datetime(2023, 1, 1),
            quantity=Decimal("100"),
            gross_transaction_amount=Decimal("1000"),
            net_cost_local=Decimal("1000"),
            net_cost=Decimal("1100"),
            trade_currency="EUR",
            portfolio_base_currency="USD",
        ),
        CostBasisTransaction(
            transaction_id="AVCO_ALLOC_BUY_2",
            portfolio_id="P_USD",
            instrument_id="EUR_ALLOC_STOCK",
            security_id="S_EUR",
            transaction_type="BUY",
            transaction_date=datetime(2023, 1, 5),
            quantity=Decimal("100"),
            gross_transaction_amount=Decimal("1200"),
            net_cost_local=Decimal("1200"),
            net_cost=Decimal("1380"),
            trade_currency="EUR",
            portfolio_base_currency="USD",
        ),
    )
    for buy in buys:
        avco_strategy.add_buy_lot(buy)

    result = avco_strategy.consume_sell_quantity_with_allocations(
        "P_USD",
        "EUR_ALLOC_STOCK",
        Decimal("50"),
    )

    assert result.legacy_tuple() == (
        Decimal("620"),
        Decimal("550"),
        Decimal("50"),
        None,
    )
    assert [allocation.source_transaction_id for allocation in result.allocations] == [
        "AVCO_ALLOC_BUY_1",
        "AVCO_ALLOC_BUY_2",
    ]
    assert [allocation.source_lot_id for allocation in result.allocations] == [
        "LOT-AVCO_ALLOC_BUY_1",
        "LOT-AVCO_ALLOC_BUY_2",
    ]
    assert [allocation.source_acquisition_date for allocation in result.allocations] == [
        date(2023, 1, 1),
        date(2023, 1, 5),
    ]
    assert [allocation.consumed_quantity for allocation in result.allocations] == [
        Decimal("25"),
        Decimal("25"),
    ]
    assert [allocation.consumed_cost_local for allocation in result.allocations] == [
        Decimal("250"),
        Decimal("300"),
    ]
    assert [allocation.consumed_cost_base for allocation in result.allocations] == [
        Decimal("275"),
        Decimal("345"),
    ]


def test_average_cost_tiny_disposal_assigns_rounding_residual_deterministically() -> None:
    strategy = AverageCostBasisStrategy()
    for transaction_id, cost in (("AVCO-TINY-1", "1"), ("AVCO-TINY-2", "2")):
        strategy.add_buy_lot(
            CostBasisTransaction(
                transaction_id=transaction_id,
                portfolio_id="P1",
                instrument_id="AVCO-TINY",
                security_id="AVCO-TINY",
                transaction_type="BUY",
                transaction_date=datetime(2026, 1, 1),
                quantity=Decimal("1"),
                gross_transaction_amount=Decimal(cost),
                net_cost=Decimal(cost),
                net_cost_local=Decimal(cost),
                trade_currency="USD",
                portfolio_base_currency="USD",
            )
        )

    result = strategy.consume_sell_quantity_with_allocations(
        "P1",
        "AVCO-TINY",
        Decimal("0.0000000001"),
    )

    assert result.error_reason is None
    assert (
        sum(
            (allocation.consumed_quantity for allocation in result.allocations),
            Decimal(0),
        )
        == result.consumed_quantity
    )
    assert (
        sum(
            (allocation.consumed_cost_local for allocation in result.allocations),
            Decimal(0),
        )
        == result.cost_local
    )
    assert (
        sum(
            (allocation.consumed_cost_base for allocation in result.allocations),
            Decimal(0),
        )
        == result.cost_base
    )
    assert strategy.get_available_quantity("P1", "AVCO-TINY") == Decimal("1.9999999999")


def test_average_cost_reconciles_negative_raw_delta_before_allocation_validation() -> None:
    strategy = AverageCostBasisStrategy()

    def add_buy(transaction_id: str, quantity: str, cost: str) -> None:
        strategy.add_buy_lot(
            CostBasisTransaction(
                transaction_id=transaction_id,
                portfolio_id="P1",
                instrument_id="AVCO-SEGMENTED",
                security_id="AVCO-SEGMENTED",
                transaction_type="BUY",
                transaction_date=datetime(2026, 1, 1),
                quantity=Decimal(quantity),
                gross_transaction_amount=Decimal(cost),
                net_cost=Decimal(cost),
                net_cost_local=Decimal(cost),
                trade_currency="USD",
                portfolio_base_currency="USD",
            )
        )

    add_buy("AVCO-SEGMENTED-1", "0.3241", "0.0004205")
    first = strategy.consume_sell_quantity_with_allocations(
        "P1",
        "AVCO-SEGMENTED",
        Decimal("0.0483839337"),
    )
    assert first.error_reason is None
    add_buy("AVCO-SEGMENTED-2", "0.05824", "0")

    second = strategy.consume_sell_quantity_with_allocations(
        "P1",
        "AVCO-SEGMENTED",
        Decimal("0.1154380503"),
    )

    assert second.error_reason is None
    assert all(allocation.consumed_quantity > 0 for allocation in second.allocations)
    assert all(allocation.consumed_cost_local >= 0 for allocation in second.allocations)
    assert all(allocation.consumed_cost_base >= 0 for allocation in second.allocations)
    assert (
        sum(
            (allocation.consumed_quantity for allocation in second.allocations),
            Decimal(0),
        )
        == second.consumed_quantity
    )
    assert (
        sum(
            (allocation.consumed_cost_local for allocation in second.allocations),
            Decimal(0),
        )
        == second.cost_local
    )
    assert (
        sum(
            (allocation.consumed_cost_base for allocation in second.allocations),
            Decimal(0),
        )
        == second.cost_base
    )
    assert strategy.get_available_quantity("P1", "AVCO-SEGMENTED") == Decimal("0.2185180160")


@pytest.mark.parametrize("strategy_type", (FIFOBasisStrategy, AverageCostBasisStrategy))
def test_source_acquisition_date_uses_canonical_utc_instant(
    strategy_type: type[FIFOBasisStrategy] | type[AverageCostBasisStrategy],
) -> None:
    strategy = strategy_type()
    strategy.add_buy_lot(
        CostBasisTransaction(
            transaction_id="OFFSET-BUY",
            portfolio_id="P1",
            instrument_id="OFFSET-INSTRUMENT",
            security_id="OFFSET-INSTRUMENT",
            transaction_type="BUY",
            transaction_date=datetime.fromisoformat("2026-01-01T23:30:00-05:00"),
            quantity=Decimal("1"),
            gross_transaction_amount=Decimal("10"),
            net_cost=Decimal("10"),
            net_cost_local=Decimal("10"),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
    )

    result = strategy.consume_sell_quantity_with_allocations(
        "P1",
        "OFFSET-INSTRUMENT",
        Decimal("1"),
    )

    assert result.allocations[0].source_acquisition_date == date(2026, 1, 2)


def test_average_cost_source_quantities_remain_exact_after_new_buy_and_disposal(
    avco_strategy: AverageCostBasisStrategy,
):
    for transaction_id, quantity, cost in (
        ("AVCO_SEQUENCE_BUY_1", "100", "1000"),
        ("AVCO_SEQUENCE_BUY_2", "100", "1200"),
    ):
        avco_strategy.add_buy_lot(
            CostBasisTransaction(
                transaction_id=transaction_id,
                portfolio_id="P1",
                instrument_id="AVCO_SEQUENCE_STOCK",
                security_id="S1",
                transaction_type="BUY",
                transaction_date=datetime(2023, 1, 1),
                quantity=Decimal(quantity),
                gross_transaction_amount=Decimal(cost),
                net_cost=Decimal(cost),
                net_cost_local=Decimal(cost),
                trade_currency="USD",
                portfolio_base_currency="USD",
            )
        )

    avco_strategy.consume_sell_quantity("P1", "AVCO_SEQUENCE_STOCK", Decimal("50"))
    avco_strategy.add_buy_lot(
        CostBasisTransaction(
            transaction_id="AVCO_SEQUENCE_BUY_3",
            portfolio_id="P1",
            instrument_id="AVCO_SEQUENCE_STOCK",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2023, 1, 2),
            quantity=Decimal("50"),
            gross_transaction_amount=Decimal("700"),
            net_cost=Decimal("700"),
            net_cost_local=Decimal("700"),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
    )
    avco_strategy.consume_sell_quantity("P1", "AVCO_SEQUENCE_STOCK", Decimal("40"))

    remaining_quantities = _open_quantities(avco_strategy)
    assert remaining_quantities == {
        "AVCO_SEQUENCE_BUY_1": Decimal("60"),
        "AVCO_SEQUENCE_BUY_2": Decimal("60"),
        "AVCO_SEQUENCE_BUY_3": Decimal("40"),
    }
    assert sum(remaining_quantities.values()) == avco_strategy.get_available_quantity(
        "P1", "AVCO_SEQUENCE_STOCK"
    )
    remaining_states = avco_strategy.get_open_lot_states()
    assert {
        transaction_id: state.cost_base for transaction_id, state in remaining_states.items()
    } == {
        "AVCO_SEQUENCE_BUY_1": Decimal("600"),
        "AVCO_SEQUENCE_BUY_2": Decimal("720"),
        "AVCO_SEQUENCE_BUY_3": Decimal("560"),
    }
    assert sum(state.cost_base for state in remaining_states.values()) == Decimal("1880")


def test_average_cost_source_quantities_reconcile_at_database_scale(
    avco_strategy: AverageCostBasisStrategy,
):
    for index in range(3):
        avco_strategy.add_buy_lot(
            CostBasisTransaction(
                transaction_id=f"AVCO_FRACTIONAL_BUY_{index}",
                portfolio_id="P1",
                instrument_id="AVCO_FRACTIONAL_STOCK",
                security_id="S1",
                transaction_type="BUY",
                transaction_date=datetime(2023, 1, 1),
                quantity=Decimal("1"),
                gross_transaction_amount=Decimal("10"),
                net_cost=Decimal("10"),
                net_cost_local=Decimal("10"),
                trade_currency="USD",
                portfolio_base_currency="USD",
            )
        )

    avco_strategy.consume_sell_quantity("P1", "AVCO_FRACTIONAL_STOCK", Decimal("1"))

    remaining_quantities = _open_quantities(avco_strategy)
    assert remaining_quantities == {
        "AVCO_FRACTIONAL_BUY_0": Decimal("0.6666666666"),
        "AVCO_FRACTIONAL_BUY_1": Decimal("0.6666666666"),
        "AVCO_FRACTIONAL_BUY_2": Decimal("0.6666666668"),
    }
    assert sum(remaining_quantities.values()) == Decimal("2")
    assert sum(
        state.cost_base for state in avco_strategy.get_open_lot_states().values()
    ) == Decimal("20")


def test_average_cost_repeating_disposal_preserves_pool_cost_identity(
    avco_strategy: AverageCostBasisStrategy,
) -> None:
    avco_strategy.add_buy_lot(
        CostBasisTransaction(
            transaction_id="AVCO_REPEATING_BUY",
            portfolio_id="P1",
            instrument_id="AVCO_REPEATING_STOCK",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2026, 7, 28),
            quantity=Decimal("3"),
            gross_transaction_amount=Decimal("100"),
            net_cost=Decimal("100"),
            net_cost_local=Decimal("100"),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
    )

    cogs_base, cogs_local, consumed_quantity, error = avco_strategy.consume_sell_quantity(
        "P1",
        "AVCO_REPEATING_STOCK",
        Decimal("1"),
    )
    open_state = avco_strategy.get_open_lot_states()["AVCO_REPEATING_BUY"]

    assert error is None
    assert consumed_quantity == Decimal("1")
    assert cogs_base == Decimal("33.3333333333")
    assert cogs_local == Decimal("33.3333333333")
    assert open_state.cost_base == Decimal("66.6666666667")
    assert open_state.cost_local == Decimal("66.6666666667")
    assert cogs_base + open_state.cost_base == Decimal("100")
    assert cogs_local + open_state.cost_local == Decimal("100")


def test_average_cost_source_allocation_is_independent_of_sell_batching() -> None:
    sequential = AverageCostBasisStrategy()
    combined = AverageCostBasisStrategy()
    for index in range(3):
        transaction = CostBasisTransaction(
            transaction_id=f"AVCO_BATCHING_BUY_{index}",
            portfolio_id="P1",
            instrument_id="AVCO_BATCHING_STOCK",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2023, 1, 1),
            quantity=Decimal("1"),
            gross_transaction_amount=Decimal("10"),
            net_cost=Decimal("10"),
            net_cost_local=Decimal("10"),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
        sequential.add_buy_lot(transaction)
        combined.add_buy_lot(transaction)

    for _ in range(10):
        sequential.consume_sell_quantity("P1", "AVCO_BATCHING_STOCK", Decimal("0.1"))
    combined.consume_sell_quantity("P1", "AVCO_BATCHING_STOCK", Decimal("1"))

    assert sequential.get_open_lot_states() == combined.get_open_lot_states()
    assert sum(state.quantity for state in sequential.get_open_lot_states().values()) == Decimal(
        "2"
    )
    assert sum(state.cost_base for state in sequential.get_open_lot_states().values()) == Decimal(
        "20"
    )


def test_average_cost_checkpoint_restore_preserves_exact_disposal_receipts() -> None:
    uninterrupted = AverageCostBasisStrategy()
    for index, (quantity, cost) in enumerate((("10", "100"), ("20", "240")), start=1):
        uninterrupted.add_buy_lot(
            CostBasisTransaction(
                transaction_id=f"AVCO-CHECKPOINT-BUY-{index}",
                portfolio_id="P1",
                instrument_id="I1",
                security_id="S1",
                transaction_type="BUY",
                transaction_date=datetime(2026, 1, index),
                quantity=Decimal(quantity),
                gross_transaction_amount=Decimal(cost),
                net_cost=Decimal(cost),
                net_cost_local=Decimal(cost),
                trade_currency="USD",
                portfolio_base_currency="USD",
            )
        )
    uninterrupted.consume_sell_quantity_with_allocations("P1", "I1", Decimal("5"))
    assert uninterrupted.transfer_basis_out("P1", "I1", Decimal("40"), Decimal("40")) is None
    checkpoint = uninterrupted.export_allocation_checkpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
    )
    restored = AverageCostBasisStrategy.from_allocation_checkpoint(checkpoint)

    uninterrupted_result = uninterrupted.consume_sell_quantity_with_allocations(
        "P1", "I1", Decimal("10")
    )
    restored_result = restored.consume_sell_quantity_with_allocations("P1", "I1", Decimal("10"))

    assert restored_result == uninterrupted_result
    assert restored.get_open_lot_states() == uninterrupted.get_open_lot_states()


def test_average_cost_checkpoint_accepts_repeating_scale_followed_by_buy() -> None:
    uninterrupted = AverageCostBasisStrategy()
    first_buy = CostBasisTransaction(
        transaction_id="AVCO-REPEATING-SCALE-BUY-1",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1),
        quantity=Decimal("3"),
        gross_transaction_amount=Decimal("30"),
        net_cost=Decimal("30"),
        net_cost_local=Decimal("30"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    uninterrupted.add_buy_lot(first_buy)
    uninterrupted.consume_sell_quantity_with_allocations("P1", "I1", Decimal("1"))
    uninterrupted.add_buy_lot(
        first_buy.model_copy(
            update={
                "transaction_id": "AVCO-REPEATING-SCALE-BUY-2",
                "transaction_date": datetime(2026, 1, 2),
            }
        )
    )

    checkpoint = uninterrupted.export_allocation_checkpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
    )
    restored = AverageCostBasisStrategy.from_allocation_checkpoint(checkpoint)

    uninterrupted_result = uninterrupted.consume_sell_quantity_with_allocations(
        "P1", "I1", Decimal("1")
    )
    restored_result = restored.consume_sell_quantity_with_allocations("P1", "I1", Decimal("1"))

    assert restored_result == uninterrupted_result
    assert restored.get_open_lot_states() == uninterrupted.get_open_lot_states()


def test_average_cost_closed_generation_checkpoint_restores_without_stale_sources() -> None:
    uninterrupted = AverageCostBasisStrategy()
    uninterrupted.add_buy_lot(
        CostBasisTransaction(
            transaction_id="AVCO-CHECKPOINT-CLOSED-BUY",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2026, 1, 1),
            quantity=Decimal("10"),
            gross_transaction_amount=Decimal("100"),
            net_cost=Decimal("100"),
            net_cost_local=Decimal("100"),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
    )
    uninterrupted.consume_sell_quantity_with_allocations("P1", "I1", Decimal("10"))
    checkpoint = uninterrupted.export_allocation_checkpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
    )

    restored = AverageCostBasisStrategy.from_allocation_checkpoint(checkpoint)

    assert checkpoint.sources == ()
    assert restored.get_open_lot_states() == {}


def test_average_cost_checkpoint_export_requires_existing_book() -> None:
    with pytest.raises(ValueError, match="checkpoint book was not found"):
        AverageCostBasisStrategy().export_allocation_checkpoint(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
        )


def test_average_cost_full_close_and_reopen_does_not_resurrect_prior_sources() -> None:
    strategy = AverageCostBasisStrategy()
    closed_source = CostBasisTransaction(
        transaction_id="AVCO_CLOSED_SOURCE",
        portfolio_id="P1",
        instrument_id="AVCO_REOPEN_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("2"),
        gross_transaction_amount=Decimal("20"),
        net_cost=Decimal("20"),
        net_cost_local=Decimal("20"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    reopened_source = closed_source.model_copy(
        update={
            "transaction_id": "AVCO_REOPENED_SOURCE",
            "quantity": Decimal("3"),
            "gross_transaction_amount": Decimal("45"),
            "net_cost": Decimal("45"),
            "net_cost_local": Decimal("45"),
        }
    )

    strategy.add_buy_lot(closed_source)
    strategy.consume_sell_quantity("P1", "AVCO_REOPEN_STOCK", Decimal("2"))
    strategy.add_buy_lot(reopened_source)
    strategy.consume_sell_quantity("P1", "AVCO_REOPEN_STOCK", Decimal("1"))

    assert strategy.get_open_lot_states() == {
        "AVCO_CLOSED_SOURCE": OpenLotState(
            original_quantity=Decimal("2"),
            quantity=Decimal("0"),
            cost_local=Decimal("0"),
            cost_base=Decimal("0"),
        ),
        "AVCO_REOPENED_SOURCE": OpenLotState(
            original_quantity=Decimal("3"),
            quantity=Decimal("2"),
            cost_local=Decimal("30"),
            cost_base=Decimal("30"),
        ),
    }


def test_average_cost_basis_transfer_restarts_disposal_segment_after_partial_sale() -> None:
    strategy = AverageCostBasisStrategy()
    strategy.add_buy_lot(
        CostBasisTransaction(
            transaction_id="AVCO-PARTIAL-BASIS-SOURCE",
            portfolio_id="P-BASIS",
            instrument_id="PARENT-SECURITY",
            security_id="PARENT-SECURITY",
            transaction_type="BUY",
            transaction_date=datetime(2026, 1, 1),
            quantity=Decimal("100"),
            gross_transaction_amount=Decimal("1000"),
            net_cost_local=Decimal("1000"),
            net_cost=Decimal("1000"),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
    )

    cogs_base, cogs_local, consumed_quantity, error = strategy.consume_sell_quantity(
        "P-BASIS",
        "PARENT-SECURITY",
        Decimal("50"),
    )
    assert (cogs_base, cogs_local, consumed_quantity, error) == (
        Decimal("500"),
        Decimal("500"),
        Decimal("50"),
        None,
    )

    assert (
        strategy.transfer_basis_out("P-BASIS", "PARENT-SECURITY", Decimal("200"), Decimal("200"))
        is None
    )
    cogs_base, cogs_local, consumed_quantity, error = strategy.consume_sell_quantity(
        "P-BASIS",
        "PARENT-SECURITY",
        Decimal("25"),
    )

    assert (cogs_base, cogs_local, consumed_quantity, error) == (
        Decimal("150"),
        Decimal("150"),
        Decimal("25"),
        None,
    )
    states = strategy.get_open_lot_states()
    assert states["AVCO-PARTIAL-BASIS-SOURCE"] == OpenLotState(
        original_quantity=Decimal("100"),
        quantity=Decimal("25"),
        cost_local=Decimal("150"),
        cost_base=Decimal("150"),
    )


@pytest.mark.parametrize("strategy_type", [FIFOBasisStrategy, AverageCostBasisStrategy])
def test_basis_only_transfer_reduces_source_lot_cost_without_changing_quantity(
    strategy_type,
) -> None:
    strategy = strategy_type()
    for transaction_id, quantity, cost in (
        ("BASIS-SOURCE-1", "60", "600"),
        ("BASIS-SOURCE-2", "40", "800"),
    ):
        strategy.add_buy_lot(
            CostBasisTransaction(
                transaction_id=transaction_id,
                portfolio_id="P-BASIS",
                instrument_id="PARENT-SECURITY",
                security_id="PARENT-SECURITY",
                transaction_type="BUY",
                transaction_date=datetime(2026, 1, 1),
                quantity=Decimal(quantity),
                gross_transaction_amount=Decimal(cost),
                net_cost_local=Decimal(cost),
                net_cost=Decimal(cost),
                trade_currency="USD",
                portfolio_base_currency="USD",
            )
        )

    error = strategy.transfer_basis_out(
        "P-BASIS",
        "PARENT-SECURITY",
        Decimal("350"),
        Decimal("350"),
    )

    assert error is None
    states = strategy.get_open_lot_states()
    assert sum(state.quantity for state in states.values()) == Decimal("100")
    assert sum(state.cost_local for state in states.values()) == Decimal("1050")
    assert sum(state.cost_base for state in states.values()) == Decimal("1050")


def _three_equal_fifo_lots() -> tuple[FIFOBasisStrategy, list[CostBasisTransaction]]:
    strategy = FIFOBasisStrategy()
    transactions = [
        CostBasisTransaction(
            transaction_id=f"FIFO-RESIDUAL-{index}",
            portfolio_id="P-BASIS",
            instrument_id="PARENT-SECURITY",
            security_id="PARENT-SECURITY",
            transaction_type="BUY",
            transaction_date=datetime(2026, 1, index),
            quantity=Decimal("1"),
            gross_transaction_amount=Decimal("2"),
            net_cost_local=Decimal("2"),
            net_cost=Decimal("1"),
            trade_currency="EUR",
            portfolio_base_currency="USD",
        )
        for index in range(1, 4)
    ]
    for transaction in transactions:
        strategy.add_buy_lot(transaction)
    return strategy, transactions


def test_fifo_basis_transfer_assigns_storage_residual_and_replays_exactly() -> None:
    strategy, transactions = _three_equal_fifo_lots()

    assert (
        strategy.transfer_basis_out(
            "P-BASIS",
            "PARENT-SECURITY",
            Decimal("1"),
            Decimal("2"),
        )
        is None
    )

    states = strategy.get_open_lot_states()
    assert [state.cost_base for state in states.values()] == [
        Decimal("0.6666666667"),
        Decimal("0.6666666667"),
        Decimal("0.6666666666"),
    ]
    assert [state.cost_local for state in states.values()] == [
        Decimal("1.3333333333"),
        Decimal("1.3333333333"),
        Decimal("1.3333333334"),
    ]
    assert sum(state.cost_base for state in states.values()) == Decimal("2.0000000000")
    assert sum(state.cost_local for state in states.values()) == Decimal("4.0000000000")

    replayed = FIFOBasisStrategy()
    replayed.restore_open_lots(
        [
            transaction.model_copy(
                update={
                    "net_cost": states[transaction.transaction_id].cost_base,
                    "net_cost_local": states[transaction.transaction_id].cost_local,
                }
            )
            for transaction in transactions
        ]
    )
    assert replayed.get_open_lot_states() == states


def test_fifo_basis_transfer_preserves_ledger_totals_across_batches() -> None:
    strategy, _ = _three_equal_fifo_lots()

    for _ in range(2):
        assert (
            strategy.transfer_basis_out(
                "P-BASIS",
                "PARENT-SECURITY",
                Decimal("0.5"),
                Decimal("1"),
            )
            is None
        )

    states = strategy.get_open_lot_states()
    assert sum(state.cost_base for state in states.values()) == Decimal("2.0000000000")
    assert sum(state.cost_local for state in states.values()) == Decimal("4.0000000000")


def test_fifo_near_full_basis_transfer_never_assigns_negative_residual() -> None:
    strategy = FIFOBasisStrategy()
    transactions = []
    for index, cost in enumerate(("3", "3", "3", "1"), start=1):
        transaction = CostBasisTransaction(
            transaction_id=f"FIFO-NEAR-FULL-{index}",
            portfolio_id="P-BASIS",
            instrument_id="PARENT-SECURITY",
            security_id="PARENT-SECURITY",
            transaction_type="BUY",
            transaction_date=datetime(2026, 2, index),
            quantity=Decimal("1"),
            gross_transaction_amount=Decimal(cost),
            net_cost_local=Decimal(cost),
            net_cost=Decimal(cost),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
        transactions.append(transaction)
        strategy.add_buy_lot(transaction)

    assert (
        strategy.transfer_basis_out(
            "P-BASIS",
            "PARENT-SECURITY",
            Decimal("9.9999999998"),
            Decimal("9.9999999998"),
        )
        is None
    )

    states = strategy.get_open_lot_states()
    assert [state.cost_base for state in states.values()] == [
        Decimal("0.0000000001"),
        Decimal("0.0000000001"),
        Decimal("0"),
        Decimal("0"),
    ]
    assert all(state.cost_base >= Decimal(0) for state in states.values())
    assert all(state.cost_local >= Decimal(0) for state in states.values())
    assert sum(state.cost_base for state in states.values()) == Decimal("0.0000000002")
    assert sum(state.cost_local for state in states.values()) == Decimal("0.0000000002")

    replayed = FIFOBasisStrategy()
    replayed.restore_open_lots(
        [
            transaction.model_copy(
                update={
                    "net_cost": states[transaction.transaction_id].cost_base,
                    "net_cost_local": states[transaction.transaction_id].cost_local,
                }
            )
            for transaction in transactions
        ]
    )
    assert replayed.get_open_lot_states() == states

    disposed_base, disposed_local, disposed_quantity, error = replayed.consume_sell_quantity(
        "P-BASIS",
        "PARENT-SECURITY",
        Decimal("4"),
    )
    assert (disposed_base, disposed_local, disposed_quantity, error) == (
        Decimal("0.0000000002"),
        Decimal("0.0000000002"),
        Decimal("4"),
        None,
    )


def test_average_cost_near_full_disposal_couples_quantity_and_basis_residuals() -> None:
    strategy = AverageCostBasisStrategy()
    transactions = []
    for index, cost in enumerate(("3", "3", "3", "1"), start=1):
        transaction = CostBasisTransaction(
            transaction_id=f"AVCO-NEAR-FULL-{index}",
            portfolio_id="P-BASIS",
            instrument_id="PARENT-SECURITY",
            security_id="PARENT-SECURITY",
            transaction_type="BUY",
            transaction_date=datetime(2026, 3, index),
            quantity=Decimal("1"),
            gross_transaction_amount=Decimal(cost),
            net_cost_local=Decimal(cost),
            net_cost=Decimal(cost),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
        transactions.append(transaction)
        strategy.add_buy_lot(transaction)

    disposed_base, disposed_local, disposed_quantity, error = strategy.consume_sell_quantity(
        "P-BASIS",
        "PARENT-SECURITY",
        Decimal("3.9999999999"),
    )
    assert (disposed_base, disposed_local, disposed_quantity, error) == (
        Decimal("9.9999999998"),
        Decimal("9.9999999998"),
        Decimal("3.9999999999"),
        None,
    )

    states = strategy.get_open_lot_states()
    assert all(state.quantity >= Decimal(0) for state in states.values())
    assert all(state.cost_base >= Decimal(0) for state in states.values())
    assert all(state.cost_local >= Decimal(0) for state in states.values())
    assert all(
        state.cost_base == Decimal(0) and state.cost_local == Decimal(0)
        for state in states.values()
        if state.quantity == Decimal(0)
    )
    assert sum(state.quantity for state in states.values()) == Decimal("0.0000000001")
    assert sum(state.cost_base for state in states.values()) == Decimal("0.0000000002")
    assert sum(state.cost_local for state in states.values()) == Decimal("0.0000000002")

    remaining_transaction = next(
        transaction
        for transaction in transactions
        if states[transaction.transaction_id].quantity > Decimal(0)
    )
    remaining_state = states[remaining_transaction.transaction_id]
    replayed = AverageCostBasisStrategy()
    replayed.restore_open_lots(
        [
            remaining_transaction.model_copy(
                update={
                    "quantity": remaining_state.quantity,
                    "source_lot_original_quantity": remaining_state.original_quantity,
                    "gross_transaction_amount": remaining_state.cost_local,
                    "net_cost": remaining_state.cost_base,
                    "net_cost_local": remaining_state.cost_local,
                }
            )
        ]
    )
    assert replayed.get_open_lot_states() == {remaining_transaction.transaction_id: remaining_state}

    close_result = replayed.consume_sell_quantity(
        "P-BASIS",
        "PARENT-SECURITY",
        Decimal("0.0000000001"),
    )
    assert close_result == (
        Decimal("0.0000000002"),
        Decimal("0.0000000002"),
        Decimal("0.0000000001"),
        None,
    )


def test_average_cost_full_basis_transfer_then_new_buy_keeps_old_source_cost_zero() -> None:
    strategy = AverageCostBasisStrategy()
    original = CostBasisTransaction(
        transaction_id="ZERO-BASIS-SOURCE",
        portfolio_id="P-BASIS",
        instrument_id="PARENT-SECURITY",
        security_id="PARENT-SECURITY",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        net_cost=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    new_buy = original.model_copy(
        update={
            "transaction_id": "POST-TRANSFER-SOURCE",
            "quantity": Decimal("20"),
            "gross_transaction_amount": Decimal("300"),
            "net_cost_local": Decimal("300"),
            "net_cost": Decimal("300"),
        }
    )

    strategy.add_buy_lot(original)
    assert (
        strategy.transfer_basis_out("P-BASIS", "PARENT-SECURITY", Decimal("1000"), Decimal("1000"))
        is None
    )
    strategy.add_buy_lot(new_buy)

    states = strategy.get_open_lot_states()
    assert states["ZERO-BASIS-SOURCE"] == OpenLotState(
        original_quantity=Decimal("100"),
        quantity=Decimal("100"),
        cost_local=Decimal("0"),
        cost_base=Decimal("0"),
    )
    assert states["POST-TRANSFER-SOURCE"] == OpenLotState(
        original_quantity=Decimal("20"),
        quantity=Decimal("20"),
        cost_local=Decimal("300"),
        cost_base=Decimal("300"),
    )

    checkpoint = strategy.export_allocation_checkpoint(
        portfolio_id="P-BASIS",
        instrument_id="PARENT-SECURITY",
        security_id="PARENT-SECURITY",
    )
    restored = AverageCostBasisStrategy.from_allocation_checkpoint(checkpoint)

    uninterrupted_result = strategy.consume_sell_quantity_with_allocations(
        "P-BASIS", "PARENT-SECURITY", Decimal("10")
    )
    restored_result = restored.consume_sell_quantity_with_allocations(
        "P-BASIS", "PARENT-SECURITY", Decimal("10")
    )

    assert restored_result == uninterrupted_result
    assert restored.get_open_lot_states() == strategy.get_open_lot_states()


@pytest.mark.parametrize("strategy_type", [FIFOBasisStrategy, AverageCostBasisStrategy])
def test_basis_transfer_rejects_amount_above_available_basis(strategy_type) -> None:
    strategy = strategy_type()
    strategy.add_buy_lot(
        CostBasisTransaction(
            transaction_id="BASIS-LIMIT-SOURCE",
            portfolio_id="P-BASIS",
            instrument_id="PARENT-SECURITY",
            security_id="PARENT-SECURITY",
            transaction_type="BUY",
            transaction_date=datetime(2026, 1, 1),
            quantity=Decimal("10"),
            gross_transaction_amount=Decimal("100"),
            net_cost_local=Decimal("100"),
            net_cost=Decimal("100"),
            trade_currency="USD",
            portfolio_base_currency="USD",
        )
    )

    error = strategy.transfer_basis_out(
        "P-BASIS", "PARENT-SECURITY", Decimal("101"), Decimal("101")
    )

    assert error is not None
    assert "exceeds available cost basis" in error
    assert strategy.get_open_lot_states()["BASIS-LIMIT-SOURCE"].cost_base == Decimal("100")


def test_average_cost_initial_lots_normalize_buy_transaction_type(
    avco_strategy: AverageCostBasisStrategy,
):
    buy_txn = CostBasisTransaction(
        transaction_id="AVCO_PADDED_BUY_1",
        portfolio_id="P1",
        instrument_id="AVCO_STOCK",
        security_id="S1",
        transaction_type=" buy ",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost_local=Decimal("1000"),
    )

    avco_strategy.set_initial_lots([buy_txn])

    assert avco_strategy.get_available_quantity("P1", "AVCO_STOCK") == Decimal("100")


@pytest.mark.parametrize("strategy_cls", [AverageCostBasisStrategy, FIFOBasisStrategy])
def test_cost_basis_strategy_rejects_dirty_negative_buy_lot_quantity(strategy_cls):
    strategy = strategy_cls()
    buy_txn = CostBasisTransaction(
        transaction_id="DIRTY_NEGATIVE_QTY_BUY",
        portfolio_id="P1",
        instrument_id="DIRTY_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    buy_txn.quantity = Decimal("-100")

    with pytest.raises(ValueError, match="positive lot quantity"):
        strategy.add_buy_lot(buy_txn)

    assert strategy.get_available_quantity("P1", "DIRTY_STOCK") == Decimal("0")


@pytest.mark.parametrize("strategy_cls", [AverageCostBasisStrategy, FIFOBasisStrategy])
def test_cost_basis_strategy_rejects_dirty_negative_buy_lot_cost_basis(strategy_cls):
    strategy = strategy_cls()
    buy_txn = CostBasisTransaction(
        transaction_id="DIRTY_NEGATIVE_COST_BUY",
        portfolio_id="P1",
        instrument_id="DIRTY_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    buy_txn.net_cost = Decimal("-1000")

    with pytest.raises(ValueError, match="non-negative lot cost basis"):
        strategy.add_buy_lot(buy_txn)

    assert strategy.get_available_quantity("P1", "DIRTY_STOCK") == Decimal("0")


@pytest.mark.parametrize("strategy_cls", [AverageCostBasisStrategy, FIFOBasisStrategy])
def test_cost_basis_strategy_normalizes_buy_lot_inputs_once(strategy_cls):
    strategy = strategy_cls()
    buy_txn = CostBasisTransaction(
        transaction_id="COUNTED_AMOUNT_BUY",
        portfolio_id="P1",
        instrument_id="COUNTED_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    quantity = _StringCountedAmount("100")
    net_cost = _StringCountedAmount("1000")
    net_cost_local = _StringCountedAmount("1000")
    buy_txn.quantity = quantity
    buy_txn.net_cost = net_cost
    buy_txn.net_cost_local = net_cost_local

    strategy.add_buy_lot(buy_txn)

    assert strategy.get_available_quantity("P1", "COUNTED_STOCK") == Decimal("100")
    assert quantity.string_call_count == 1
    assert net_cost.string_call_count == 1
    assert net_cost_local.string_call_count == 1


@pytest.mark.parametrize("strategy_cls", [AverageCostBasisStrategy, FIFOBasisStrategy])
def test_cost_basis_strategy_rejects_non_positive_sell_quantity_without_state_change(
    strategy_cls,
):
    strategy = strategy_cls()
    buy_txn = CostBasisTransaction(
        transaction_id="SELL_GUARD_BUY",
        portfolio_id="P1",
        instrument_id="SELL_GUARD_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    strategy.add_buy_lot(buy_txn)

    cogs_base, cogs_local, consumed_quantity, error = strategy.consume_sell_quantity(
        portfolio_id="P1",
        instrument_id="SELL_GUARD_STOCK",
        sell_quantity=Decimal("-10"),
    )

    assert cogs_base == Decimal("0")
    assert cogs_local == Decimal("0")
    assert consumed_quantity == Decimal("0")
    assert error == "Sell quantity (-10) must not be negative."
    assert strategy.get_available_quantity("P1", "SELL_GUARD_STOCK") == Decimal("100")


# --- Tests for FIFOBasisStrategy ---


@pytest.fixture
def fifo_strategy() -> FIFOBasisStrategy:
    """Provides a clean instance of the FIFOBasisStrategy."""
    return FIFOBasisStrategy()


@pytest.fixture
def sample_buy_transaction() -> CostBasisTransaction:
    """Provides a sample BUY transaction for FIFO tests."""
    return CostBasisTransaction(
        transaction_id="FIFO_BUY_01",
        portfolio_id="P1",
        instrument_id="FIFO_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1010"),  # Includes $10 fee
        net_cost_local=Decimal("1010"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )


def test_fifo_add_buy_lot(
    fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: CostBasisTransaction
):
    # Act
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Assert
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("100")
    lot_key = ("P1", "FIFO_STOCK")
    assert len(fifo_strategy._open_lots[lot_key]) == 1
    lot = fifo_strategy._open_lots[lot_key][0]
    assert lot.cost_per_share_base == Decimal("10.10")  # 1010 / 100


def test_fifo_initial_lots_normalize_buy_transaction_type(
    fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: CostBasisTransaction
):
    padded_buy = sample_buy_transaction.model_copy(update={"transaction_type": " buy "})

    fifo_strategy.set_initial_lots([padded_buy])

    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("100")
    lot = fifo_strategy._open_lots[("P1", "FIFO_STOCK")][0]
    assert lot.transaction_id == "FIFO_BUY_01"


def test_fifo_consume_sell_fully(
    fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: CostBasisTransaction
):
    # Arrange
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Act
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("100")
    )

    # Assert
    assert cost_base == Decimal("1010")
    assert consumed_qty == Decimal("100")
    assert error is None
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("0")


def test_fifo_consume_sell_partially(
    fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: CostBasisTransaction
):
    # Arrange
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Act
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("40")
    )

    # Assert
    assert cost_base == Decimal("404")  # 40 shares * $10.10/share
    assert consumed_qty == Decimal("40")
    assert error is None
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("60")
    lot_key = ("P1", "FIFO_STOCK")
    assert fifo_strategy._open_lots[lot_key][0].remaining_quantity == Decimal("60")


def test_fifo_repeating_unit_cost_allocates_rounding_residual_to_open_lot(
    fifo_strategy: FIFOBasisStrategy,
    sample_buy_transaction: CostBasisTransaction,
) -> None:
    repeating_cost_buy = sample_buy_transaction.model_copy(
        update={
            "quantity": Decimal("3"),
            "net_cost": Decimal("100"),
            "net_cost_local": Decimal("100"),
        }
    )
    fifo_strategy.add_buy_lot(repeating_cost_buy)

    cost_base, cost_local, consumed_quantity, error = fifo_strategy.consume_sell_quantity(
        "P1",
        "FIFO_STOCK",
        Decimal("1"),
    )
    open_state = fifo_strategy.get_open_lot_states()["FIFO_BUY_01"]

    assert error is None
    assert consumed_quantity == Decimal("1")
    assert cost_base == Decimal("33.3333333333")
    assert cost_local == Decimal("33.3333333333")
    assert open_state.cost_base == Decimal("66.6666666667")
    assert open_state.cost_local == Decimal("66.6666666667")
    assert cost_base + open_state.cost_base == Decimal("100")
    assert cost_local + open_state.cost_local == Decimal("100")


def test_fifo_consume_sell_insufficient_quantity(
    fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: CostBasisTransaction
):
    # Arrange
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Act
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("101")
    )

    # Assert
    assert cost_base == Decimal("0")
    assert consumed_qty == Decimal("0")
    assert error == "Sell quantity (101) exceeds available holdings (100)."
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("100")


def test_fifo_multi_lot_disposition(fifo_strategy: FIFOBasisStrategy):
    # Arrange: Two buy lots
    buy1 = CostBasisTransaction(
        transaction_id="FIFO_BUY_01",
        portfolio_id="P1",
        instrument_id="FIFO_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )  # Cost: $10/share
    buy2 = CostBasisTransaction(
        transaction_id="FIFO_BUY_02",
        portfolio_id="P1",
        instrument_id="FIFO_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("50"),
        gross_transaction_amount=Decimal("600"),
        net_cost=Decimal("600"),
        net_cost_local=Decimal("600"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )  # Cost: $12/share

    fifo_strategy.add_buy_lot(buy1)
    fifo_strategy.add_buy_lot(buy2)
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("150")

    # Act: Sell 120 shares. This should consume all of buy1 and 20 shares of buy2.
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("120")
    )

    # Assert
    # COGS = (100 shares * $10) + (20 shares * $12) = 1000 + 240 = 1240
    assert cost_base == Decimal("1240")
    assert consumed_qty == Decimal("120")
    assert error is None
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("30")
    lot_key = ("P1", "FIFO_STOCK")
    assert len(fifo_strategy._open_lots[lot_key]) == 1
    assert fifo_strategy._open_lots[lot_key][0].remaining_quantity == Decimal("30")


def test_fifo_disposition_exposes_ordered_source_lot_allocations(
    fifo_strategy: FIFOBasisStrategy,
) -> None:
    buy1 = CostBasisTransaction(
        transaction_id="FIFO_ALLOC_BUY_01",
        portfolio_id="P1",
        instrument_id="FIFO_ALLOC_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1100"),
        net_cost_local=Decimal("1000"),
        trade_currency="EUR",
        portfolio_base_currency="USD",
    )
    buy2 = buy1.model_copy(
        update={
            "transaction_id": "FIFO_ALLOC_BUY_02",
            "transaction_date": datetime(2023, 1, 2),
            "quantity": Decimal("50"),
            "gross_transaction_amount": Decimal("600"),
            "net_cost": Decimal("690"),
            "net_cost_local": Decimal("600"),
        }
    )
    fifo_strategy.add_buy_lot(buy1)
    fifo_strategy.add_buy_lot(buy2)

    result = fifo_strategy.consume_sell_quantity_with_allocations(
        "P1",
        "FIFO_ALLOC_STOCK",
        Decimal("120"),
    )

    assert result.legacy_tuple() == (
        Decimal("1376"),
        Decimal("1240"),
        Decimal("120"),
        None,
    )
    assert [allocation.source_transaction_id for allocation in result.allocations] == [
        "FIFO_ALLOC_BUY_01",
        "FIFO_ALLOC_BUY_02",
    ]
    assert [allocation.source_lot_id for allocation in result.allocations] == [
        "LOT-FIFO_ALLOC_BUY_01",
        "LOT-FIFO_ALLOC_BUY_02",
    ]
    assert [allocation.source_acquisition_date for allocation in result.allocations] == [
        date(2023, 1, 1),
        date(2023, 1, 2),
    ]
    assert [allocation.allocation_ordinal for allocation in result.allocations] == [1, 2]
    assert [allocation.consumed_quantity for allocation in result.allocations] == [
        Decimal("100"),
        Decimal("20"),
    ]
    assert [allocation.consumed_cost_local for allocation in result.allocations] == [
        Decimal("1000"),
        Decimal("240"),
    ]
    assert [allocation.consumed_cost_base for allocation in result.allocations] == [
        Decimal("1100"),
        Decimal("276"),
    ]


def test_fifo_available_quantity_does_not_scan_open_lots(
    fifo_strategy: FIFOBasisStrategy,
    sample_buy_transaction: CostBasisTransaction,
) -> None:
    class IterationForbiddenDeque(deque):
        def __iter__(self):
            raise AssertionError("available quantity must not scan open lots")

    second_buy = sample_buy_transaction.model_copy(update={"transaction_id": "FIFO_BUY_02"})
    fifo_strategy.add_buy_lot(sample_buy_transaction)
    fifo_strategy.add_buy_lot(second_buy)
    lot_key = ("P1", "FIFO_STOCK")
    fifo_strategy._open_lots[lot_key] = IterationForbiddenDeque(fifo_strategy._open_lots[lot_key])

    assert fifo_strategy.get_available_quantity(*lot_key) == Decimal("200")
    _, _, consumed_quantity, error = fifo_strategy.consume_sell_quantity(*lot_key, Decimal("40"))

    assert error is None
    assert consumed_quantity == Decimal("40")
    assert fifo_strategy.get_available_quantity(*lot_key) == Decimal("160")


# --- NEW TEST ---
def test_fifo_dual_currency_disposition(fifo_strategy: FIFOBasisStrategy):
    """
    Tests FIFO with a USD portfolio trading a EUR stock with changing FX rates.
    """
    # ARRANGE
    # Lot 1: 100 shares @ €10/share, FX=1.10. Cost: €1000 local, $1100 base.
    buy1 = CostBasisTransaction(
        transaction_id="FIFO_DC_BUY_1",
        portfolio_id="P_USD",
        instrument_id="EUR_STOCK",
        security_id="S_EUR",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        net_cost=Decimal("1100"),
        trade_currency="EUR",
        portfolio_base_currency="USD",
    )
    # Lot 2: 50 shares @ €12/share, FX=1.15. Cost: €600 local, $690 base.
    buy2 = CostBasisTransaction(
        transaction_id="FIFO_DC_BUY_2",
        portfolio_id="P_USD",
        instrument_id="EUR_STOCK",
        security_id="S_EUR",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("50"),
        gross_transaction_amount=Decimal("600"),
        net_cost_local=Decimal("600"),
        net_cost=Decimal("690"),
        trade_currency="EUR",
        portfolio_base_currency="USD",
    )
    fifo_strategy.add_buy_lot(buy1)
    fifo_strategy.add_buy_lot(buy2)
    assert fifo_strategy.get_available_quantity("P_USD", "EUR_STOCK") == Decimal("150")

    # ACT: Sell 120 shares. This should consume all of Lot 1 and 20 shares of Lot 2.
    cogs_base, cogs_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P_USD", "EUR_STOCK", Decimal("120")
    )

    # ASSERT
    assert error is None
    assert consumed_qty == Decimal("120")

    # COGS Local: (100 shares * €10) + (20 shares * €12) = €1000 + €240 = €1240
    assert cogs_local == pytest.approx(Decimal("1240"))

    # COGS Base: (100 shares * $11) + (20 shares * $13.80) = $1100 + $276 = $1376
    # Note: Cost per share for Lot 2 is $690/50 = $13.80
    assert cogs_base == pytest.approx(Decimal("1376"))

    # Assert final state: 30 shares from Lot 2 should remain
    assert fifo_strategy.get_available_quantity("P_USD", "EUR_STOCK") == Decimal("30")
    remaining_lot = fifo_strategy._open_lots[("P_USD", "EUR_STOCK")][0]
    assert remaining_lot.transaction_id == "FIFO_DC_BUY_2"
    assert remaining_lot.remaining_quantity == Decimal("30")
