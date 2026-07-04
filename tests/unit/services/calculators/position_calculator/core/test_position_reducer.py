from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.calculators.position_calculator.app.core.position_reducer import (
    PositionBalanceState,
    calculate_next_position_state,
    cash_position_deltas,
    plan_backdated_replay,
)


def _txn(
    transaction_type: str,
    *,
    quantity: Decimal = Decimal("0"),
    gross_transaction_amount: Decimal = Decimal("0"),
    net_cost: Decimal | None = None,
    net_cost_local: Decimal | None = None,
    movement_direction: str | None = None,
    component_type: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_type=transaction_type,
        component_type=component_type,
        quantity=quantity,
        gross_transaction_amount=gross_transaction_amount,
        net_cost=net_cost,
        net_cost_local=net_cost_local,
        movement_direction=movement_direction,
    )


def test_calculate_next_position_state_applies_buy_and_sell_net_costs() -> None:
    initial_state = PositionBalanceState(
        quantity=Decimal("100"),
        cost_basis=Decimal("1200"),
        cost_basis_local=Decimal("1000"),
    )

    bought_state = calculate_next_position_state(
        initial_state,
        _txn(
            "BUY",
            quantity=Decimal("10"),
            net_cost=Decimal("125"),
            net_cost_local=Decimal("100"),
        ),
    )
    sold_state = calculate_next_position_state(
        bought_state,
        _txn(
            "SELL",
            quantity=Decimal("40"),
            net_cost=Decimal("-450"),
            net_cost_local=Decimal("-400"),
        ),
    )

    assert bought_state == PositionBalanceState(
        quantity=Decimal("110"),
        cost_basis=Decimal("1325"),
        cost_basis_local=Decimal("1100"),
    )
    assert sold_state == PositionBalanceState(
        quantity=Decimal("70"),
        cost_basis=Decimal("875"),
        cost_basis_local=Decimal("700"),
    )


def test_cash_reducer_uses_movement_direction_and_booked_costs() -> None:
    initial_state = PositionBalanceState(
        quantity=Decimal("1000"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )

    next_state = calculate_next_position_state(
        initial_state,
        _txn(
            "ADJUSTMENT",
            quantity=Decimal("0"),
            gross_transaction_amount=Decimal("25"),
            net_cost=Decimal("0"),
            net_cost_local=Decimal("0"),
            movement_direction=" outflow ",
        ),
    )

    assert next_state == PositionBalanceState(
        quantity=Decimal("975"),
        cost_basis=Decimal("975"),
        cost_basis_local=Decimal("975"),
    )


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected_quantity"),
    [
        ("TRANSFER_IN", Decimal("5"), Decimal("105")),
        ("TRANSFER_OUT", Decimal("5"), Decimal("95")),
        ("RIGHTS_ALLOCATE", Decimal("2"), Decimal("102")),
        ("RIGHTS_SUBSCRIBE", Decimal("2"), Decimal("98")),
    ],
)
def test_transfer_reducer_applies_inflow_and_outflow_direction(
    transaction_type: str,
    quantity: Decimal,
    expected_quantity: Decimal,
) -> None:
    initial_state = PositionBalanceState(
        quantity=Decimal("100"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )

    next_state = calculate_next_position_state(
        initial_state,
        _txn(
            transaction_type,
            quantity=quantity,
            gross_transaction_amount=Decimal("20"),
        ),
    )

    assert next_state.quantity == expected_quantity


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected_quantity"),
    [
        ("SPLIT", Decimal("10"), Decimal("110")),
        ("BONUS_ISSUE", Decimal("8"), Decimal("108")),
        ("REVERSE_SPLIT", Decimal("15"), Decimal("85")),
        ("CONSOLIDATION", Decimal("12"), Decimal("88")),
    ],
)
def test_same_instrument_corporate_actions_are_quantity_only(
    transaction_type: str,
    quantity: Decimal,
    expected_quantity: Decimal,
) -> None:
    initial_state = PositionBalanceState(
        quantity=Decimal("100"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )

    next_state = calculate_next_position_state(
        initial_state,
        _txn(transaction_type, quantity=quantity),
    )

    assert next_state == PositionBalanceState(
        quantity=expected_quantity,
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )


def test_spin_off_reducer_moves_basis_without_quantity_when_quantity_is_zero() -> None:
    initial_state = PositionBalanceState(
        quantity=Decimal("100"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )

    next_state = calculate_next_position_state(
        initial_state,
        _txn(
            "SPIN_OFF",
            quantity=Decimal("0"),
            gross_transaction_amount=Decimal("250"),
            net_cost=Decimal("-250"),
            net_cost_local=Decimal("-250"),
        ),
    )

    assert next_state == PositionBalanceState(
        quantity=Decimal("100"),
        cost_basis=Decimal("750"),
        cost_basis_local=Decimal("750"),
    )


def test_fx_reducer_tracks_contract_open_close_from_component_type() -> None:
    initial_state = PositionBalanceState()

    open_state = calculate_next_position_state(
        initial_state,
        _txn("FX_FORWARD", component_type="FX_CONTRACT_OPEN"),
    )
    close_state = calculate_next_position_state(
        open_state,
        _txn("FX_FORWARD", component_type="FX_CONTRACT_CLOSE"),
    )

    assert open_state.quantity == Decimal("1")
    assert close_state == PositionBalanceState()


def test_flat_position_zeroes_residual_cost_basis() -> None:
    next_state = calculate_next_position_state(
        PositionBalanceState(
            quantity=Decimal("5"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        ),
        _txn(
            "SELL",
            quantity=Decimal("5"),
            net_cost=Decimal("-80"),
            net_cost_local=Decimal("-70"),
        ),
    )

    assert next_state == PositionBalanceState()


def test_cash_position_deltas_normalize_booked_costs_once() -> None:
    class CountedAmount:
        def __init__(self, value: str) -> None:
            self.value = value
            self.string_call_count = 0

        def __str__(self) -> str:
            self.string_call_count += 1
            return self.value

    net_cost = CountedAmount("30")
    net_cost_local = CountedAmount("30")
    transaction = _txn(
        "DEPOSIT",
        quantity=Decimal("25"),
        gross_transaction_amount=Decimal("0"),
        net_cost=net_cost,
        net_cost_local=net_cost_local,
    )

    quantity_delta, cost_basis_delta, cost_basis_local_delta = cash_position_deltas(
        transaction, "DEPOSIT"
    )

    assert quantity_delta == Decimal("25")
    assert cost_basis_delta == Decimal("30")
    assert cost_basis_local_delta == Decimal("30")
    assert net_cost.string_call_count == 1
    assert net_cost_local.string_call_count == 1


def test_plan_backdated_replay_queues_original_event_before_effective_completion() -> None:
    decision = plan_backdated_replay(
        event_epoch=None,
        transaction_date=date(2026, 3, 10),
        current_watermark_date=date(2026, 3, 31),
        latest_position_history_date=date(2026, 3, 20),
        latest_completed_snapshot_date=date(2026, 4, 1),
    )

    assert decision.should_queue_replay is True
    assert decision.effective_completed_date == date(2026, 4, 1)
    assert decision.replay_watermark_date == date(2026, 3, 9)
    assert decision.reason == "original_backdated_transaction"


@pytest.mark.parametrize(
    ("event_epoch", "transaction_date"),
    [
        (1, date(2026, 3, 10)),
        (None, date(2026, 4, 1)),
    ],
)
def test_plan_backdated_replay_skips_current_epoch_or_current_date_events(
    event_epoch: int | None,
    transaction_date: date,
) -> None:
    decision = plan_backdated_replay(
        event_epoch=event_epoch,
        transaction_date=transaction_date,
        current_watermark_date=date(2026, 3, 31),
        latest_position_history_date=None,
        latest_completed_snapshot_date=date(2026, 4, 1),
    )

    assert decision.should_queue_replay is False
    assert decision.effective_completed_date == date(2026, 4, 1)
    assert decision.replay_watermark_date is None
    assert decision.reason == "current_or_replay_event"
