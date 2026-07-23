"""Executable contract proof for the finite cost-ledger migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c120b2c3d4f9_fix_enforce_finite_cost_ledger_values.py"
)


def test_finite_cost_ledger_migration_is_bounded_and_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition, **kwargs: operations.append(
            ("create", table, name, condition, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "execute",
        lambda statement: operations.append(("execute", statement)),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop", table, name, kwargs)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c120b2c3d4f9"
    assert migration["down_revision"] == "c119b2c3d4f8"
    creates = [operation for operation in operations if operation[0] == "create"]
    validates = [operation for operation in operations if operation[0] == "execute"]
    drops = [operation for operation in operations if operation[0] == "drop"]
    assert len(creates) == len(drops) == 12
    assert len(validates) == 6
    assert {operation[1] for operation in creates} == {
        "transactions",
        "transaction_costs",
        "position_lot_state",
        "cost_basis_processing_state",
        "average_cost_pool_state",
        "accrued_income_offset_state",
    }
    assert all(operation[4] == {"postgresql_not_valid": True} for operation in creates)
    assert validates == [
        (
            "execute",
            'ALTER TABLE "transactions" '
            'VALIDATE CONSTRAINT "ck_transactions_quantity_finite", '
            'VALIDATE CONSTRAINT "ck_transactions_quantity_nonnegative"',
        ),
        (
            "execute",
            'ALTER TABLE "transaction_costs" '
            'VALIDATE CONSTRAINT "ck_transaction_costs_amount_finite"',
        ),
        (
            "execute",
            'ALTER TABLE "position_lot_state" '
            'VALIDATE CONSTRAINT "ck_position_lot_state_numeric_finite", '
            'VALIDATE CONSTRAINT "ck_position_lot_original_quantity_nonnegative", '
            'VALIDATE CONSTRAINT "ck_position_lot_accrued_interest_nonnegative"',
        ),
        (
            "execute",
            'ALTER TABLE "cost_basis_processing_state" '
            'VALIDATE CONSTRAINT "ck_cost_basis_processing_quantity_finite", '
            'VALIDATE CONSTRAINT "ck_cost_basis_processing_quantity_nonnegative"',
        ),
        (
            "execute",
            'ALTER TABLE "average_cost_pool_state" '
            'VALIDATE CONSTRAINT "ck_average_cost_pool_numeric_finite"',
        ),
        (
            "execute",
            'ALTER TABLE "accrued_income_offset_state" '
            'VALIDATE CONSTRAINT "ck_accrued_income_offset_numeric_finite", '
            'VALIDATE CONSTRAINT "ck_accrued_income_paid_nonnegative", '
            'VALIDATE CONSTRAINT "ck_accrued_income_remaining_nonnegative"',
        ),
    ]
    assert [operation[2] for operation in drops] == [
        operation[2] for operation in reversed(creates)
    ]
    assert all(operation[3] == {"type_": "check"} for operation in drops)
