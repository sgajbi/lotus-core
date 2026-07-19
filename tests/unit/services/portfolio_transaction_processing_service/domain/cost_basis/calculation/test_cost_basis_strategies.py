"""Verify domain-owned FIFO and average-cost strategy behavior."""

from collections import deque
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostBasisStrategy,
    CostBasisTransaction,
    FIFOBasisStrategy,
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
            quantity=Decimal("0"),
            cost_local=Decimal("0"),
            cost_base=Decimal("0"),
        ),
        "AVCO_REOPENED_SOURCE": OpenLotState(
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
        quantity=Decimal("100"),
        cost_local=Decimal("0"),
        cost_base=Decimal("0"),
    )
    assert states["POST-TRANSFER-SOURCE"] == OpenLotState(
        quantity=Decimal("20"),
        cost_local=Decimal("300"),
        cost_base=Decimal("300"),
    )


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
