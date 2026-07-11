"""Verify ORM metadata carries cost and lot ledger integrity constraints."""

from portfolio_common.database_models import PositionLotState, TransactionCost


def _constraint_names(model: type) -> set[str]:
    return {
        constraint.name for constraint in model.__table__.constraints if constraint.name is not None
    }


def test_transaction_cost_requires_positive_component_amount() -> None:
    assert "ck_transaction_costs_amount_positive" in _constraint_names(TransactionCost)


def test_position_lot_state_enforces_quantity_and_cost_bounds() -> None:
    assert {
        "ck_position_lot_open_quantity_nonnegative",
        "ck_position_lot_open_not_above_original",
        "ck_position_lot_local_cost_nonnegative",
        "ck_position_lot_base_cost_nonnegative",
    } <= _constraint_names(PositionLotState)
