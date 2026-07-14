"""Test deterministic position state transitions and replay decisions."""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.position.reducer import (
    PositionBalanceState,
    calculate_next_position_state,
    cash_position_deltas,
    plan_backdated_recalculation,
)

REPO_ROOT = Path(__file__).resolve().parents[6]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
TARGET_TEST = SERVICE_TEST_ROOT / "domain/position/test_reducer.py"
RETIRED_TEST = SERVICE_TEST_ROOT / "position/test_position_reducer.py"


def test_position_reducer_tests_are_owned_by_domain_boundary() -> None:
    assert Path(__file__).resolve() == TARGET_TEST.resolve()
    assert not RETIRED_TEST.exists()


def _txn(
    transaction_type: str,
    *,
    quantity: Decimal = Decimal("0"),
    gross_transaction_amount: Decimal = Decimal("0"),
    net_cost: Decimal | None = None,
    net_cost_local: Decimal | None = None,
    movement_direction: str | None = None,
    component_type: str | None = None,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"TX-{transaction_type}",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=quantity,
        price=Decimal("1"),
        gross_transaction_amount=gross_transaction_amount,
        trade_currency="SGD",
        currency="SGD",
        net_cost=net_cost,
        net_cost_local=net_cost_local,
        movement_direction=movement_direction,
        component_type=component_type,
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


def test_calculate_next_position_state_normalizes_transaction_type() -> None:
    next_state = calculate_next_position_state(
        PositionBalanceState(
            quantity=Decimal("10"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        ),
        _txn(
            " buy ",
            quantity=Decimal("5"),
            net_cost=Decimal("55"),
            net_cost_local=Decimal("55"),
        ),
    )

    assert next_state == PositionBalanceState(
        quantity=Decimal("15"),
        cost_basis=Decimal("155"),
        cost_basis_local=Decimal("155"),
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
        ("MERGER_IN", Decimal("5"), Decimal("105")),
        ("MERGER_OUT", Decimal("5"), Decimal("95")),
        ("EXCHANGE_IN", Decimal("5"), Decimal("105")),
        ("EXCHANGE_OUT", Decimal("5"), Decimal("95")),
        ("REPLACEMENT_IN", Decimal("5"), Decimal("105")),
        ("REPLACEMENT_OUT", Decimal("5"), Decimal("95")),
        ("SPIN_IN", Decimal("5"), Decimal("105")),
        ("DEMERGER_IN", Decimal("5"), Decimal("105")),
        ("RIGHTS_ALLOCATE", Decimal("2"), Decimal("102")),
        ("RIGHTS_SHARE_DELIVERY", Decimal("2"), Decimal("102")),
        ("RIGHTS_SUBSCRIBE", Decimal("2"), Decimal("98")),
        ("RIGHTS_SELL", Decimal("2"), Decimal("98")),
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
        ("STOCK_DIVIDEND", Decimal("5"), Decimal("105")),
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


def test_fx_cash_settlement_buy_updates_cash_position() -> None:
    next_state = calculate_next_position_state(
        PositionBalanceState(
            quantity=Decimal("1000"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
        ),
        _txn(
            "FX_FORWARD",
            gross_transaction_amount=Decimal("1095"),
            component_type="FX_CASH_SETTLEMENT_BUY",
        ),
    )

    assert next_state == PositionBalanceState(
        quantity=Decimal("2095"),
        cost_basis=Decimal("2095"),
        cost_basis_local=Decimal("2095"),
    )


@pytest.mark.parametrize(
    ("transaction_type", "gross_amount", "expected_balance"),
    [
        ("DEPOSIT", Decimal("25"), Decimal("125")),
        ("WITHDRAWAL", Decimal("30"), Decimal("70")),
        ("FEE", Decimal("5"), Decimal("95")),
        ("TAX", Decimal("7"), Decimal("93")),
    ],
)
def test_cash_portfolio_flows_use_gross_amount_when_booked_cost_is_absent(
    transaction_type: str,
    gross_amount: Decimal,
    expected_balance: Decimal,
) -> None:
    next_state = calculate_next_position_state(
        PositionBalanceState(
            quantity=Decimal("100"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        ),
        _txn(transaction_type, gross_transaction_amount=gross_amount),
    )

    assert next_state == PositionBalanceState(
        quantity=expected_balance,
        cost_basis=expected_balance,
        cost_basis_local=expected_balance,
    )


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected_balance"),
    [
        ("DEPOSIT", Decimal("25"), Decimal("125")),
        ("WITHDRAWAL", Decimal("30"), Decimal("70")),
        ("FEE", Decimal("5"), Decimal("95")),
        ("TAX", Decimal("7"), Decimal("93")),
    ],
)
def test_cash_portfolio_flows_use_quantity_when_gross_and_booked_cost_are_zero(
    transaction_type: str,
    quantity: Decimal,
    expected_balance: Decimal,
) -> None:
    next_state = calculate_next_position_state(
        PositionBalanceState(
            quantity=Decimal("100"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        ),
        _txn(
            transaction_type,
            quantity=quantity,
            net_cost=Decimal("0"),
            net_cost_local=Decimal("0"),
        ),
    )

    assert next_state == PositionBalanceState(
        quantity=expected_balance,
        cost_basis=expected_balance,
        cost_basis_local=expected_balance,
    )


def test_cash_fee_uses_fee_inclusive_booked_cost() -> None:
    next_state = calculate_next_position_state(
        PositionBalanceState(
            quantity=Decimal("100"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        ),
        _txn(
            "FEE",
            gross_transaction_amount=Decimal("25"),
            net_cost=Decimal("-26.75"),
            net_cost_local=Decimal("-26.75"),
        ),
    )

    assert next_state == PositionBalanceState(
        quantity=Decimal("73.25"),
        cost_basis=Decimal("73.25"),
        cost_basis_local=Decimal("73.25"),
    )


def test_foreign_currency_cash_flow_preserves_base_and_local_booked_costs() -> None:
    deposited_state = calculate_next_position_state(
        PositionBalanceState(),
        _txn(
            "DEPOSIT",
            quantity=Decimal("335000"),
            gross_transaction_amount=Decimal("335000"),
            net_cost=Decimal("359349.475"),
            net_cost_local=Decimal("335000"),
        ),
    )
    sold_state = calculate_next_position_state(
        deposited_state,
        _txn(
            "SELL",
            quantity=Decimal("82552"),
            gross_transaction_amount=Decimal("82552"),
            net_cost=Decimal("-88689.906304"),
            net_cost_local=Decimal("-82552"),
        ),
    )

    assert deposited_state == PositionBalanceState(
        quantity=Decimal("335000"),
        cost_basis=Decimal("359349.475"),
        cost_basis_local=Decimal("335000"),
    )
    assert sold_state == PositionBalanceState(
        quantity=Decimal("252448"),
        cost_basis=Decimal("270659.568696"),
        cost_basis_local=Decimal("252448"),
    )


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


def test_cash_position_deltas_use_canonical_booked_decimal_amounts() -> None:
    transaction = _txn(
        "DEPOSIT",
        quantity=Decimal("25"),
        gross_transaction_amount=Decimal("0"),
        net_cost=Decimal("30"),
        net_cost_local=Decimal("30"),
    )

    quantity_delta, cost_basis_delta, cost_basis_local_delta = cash_position_deltas(
        transaction, "DEPOSIT"
    )

    assert quantity_delta == Decimal("25")
    assert cost_basis_delta == Decimal("30")
    assert cost_basis_local_delta == Decimal("30")


def test_plan_backdated_recalculation_rebuilds_original_event_before_effective_completion() -> None:
    decision = plan_backdated_recalculation(
        event_epoch=None,
        transaction_date=date(2026, 3, 10),
        current_watermark_date=date(2026, 3, 31),
        latest_position_history_date=date(2026, 3, 20),
        latest_completed_snapshot_date=date(2026, 4, 1),
    )

    assert decision.should_recalculate is True
    assert decision.effective_completed_date == date(2026, 4, 1)
    assert decision.recalculation_watermark_date == date(2026, 3, 9)
    assert decision.reason == "original_backdated_transaction"


@pytest.mark.parametrize(
    ("event_epoch", "transaction_date"),
    [
        (1, date(2026, 3, 10)),
        (None, date(2026, 4, 1)),
    ],
)
def test_plan_backdated_recalculation_skips_current_epoch_or_current_date_events(
    event_epoch: int | None,
    transaction_date: date,
) -> None:
    decision = plan_backdated_recalculation(
        event_epoch=event_epoch,
        transaction_date=transaction_date,
        current_watermark_date=date(2026, 3, 31),
        latest_position_history_date=None,
        latest_completed_snapshot_date=date(2026, 4, 1),
    )

    assert decision.should_recalculate is False
    assert decision.effective_completed_date == date(2026, 4, 1)
    assert decision.recalculation_watermark_date is None
    assert decision.reason == "current_or_replay_event"
