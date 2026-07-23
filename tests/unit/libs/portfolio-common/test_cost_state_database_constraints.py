"""Verify ORM metadata carries cost and lot ledger integrity constraints."""

import pytest
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    AverageCostPoolState,
    CostBasisProcessingState,
    PositionLotState,
    Transaction,
    TransactionCost,
)
from sqlalchemy import CheckConstraint


def _constraint_names(model: type) -> set[str]:
    return {
        constraint.name for constraint in model.__table__.constraints if constraint.name is not None
    }


def _check_sql(model: type, constraint_name: str) -> str:
    constraint = next(
        constraint
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == constraint_name
    )
    return str(constraint.sqltext)


def test_transaction_cost_requires_positive_component_amount() -> None:
    assert "ck_transaction_costs_amount_positive" in _constraint_names(TransactionCost)


def test_position_lot_state_enforces_quantity_and_cost_bounds() -> None:
    assert {
        "ck_position_lot_open_quantity_nonnegative",
        "ck_position_lot_open_not_above_original",
        "ck_position_lot_local_cost_nonnegative",
        "ck_position_lot_base_cost_nonnegative",
    } <= _constraint_names(PositionLotState)


@pytest.mark.parametrize(
    ("model", "constraint_name", "column_names"),
    [
        (Transaction, "ck_transactions_quantity_finite", ["quantity"]),
        (TransactionCost, "ck_transaction_costs_amount_finite", ["amount"]),
        (
            PositionLotState,
            "ck_position_lot_state_numeric_finite",
            [
                "original_quantity",
                "open_quantity",
                "lot_cost_local",
                "lot_cost_base",
                "accrued_interest_paid_local",
            ],
        ),
        (
            CostBasisProcessingState,
            "ck_cost_basis_processing_quantity_finite",
            ["latest_quantity"],
        ),
        (
            AverageCostPoolState,
            "ck_average_cost_pool_numeric_finite",
            ["pool_quantity", "pool_cost_local", "pool_cost_base"],
        ),
        (
            AccruedIncomeOffsetState,
            "ck_accrued_income_offset_numeric_finite",
            ["accrued_interest_paid_local", "remaining_offset_local"],
        ),
    ],
)
def test_cost_ledger_numeric_constraints_reject_non_finite_values(
    model: type,
    constraint_name: str,
    column_names: list[str],
) -> None:
    constraint_sql = _check_sql(model, constraint_name)

    assert all(f"CAST({column_name} AS TEXT)" in constraint_sql for column_name in column_names)
    assert all(marker in constraint_sql for marker in ("'NaN'", "'Infinity'", "'-Infinity'"))
