"""Executable migration contract for canonical redemption terms."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import Column, Numeric

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c145b2c3d512_feat_add_redemption_terms.py"
)


def test_redemption_terms_migration_is_additive_constrained_and_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(("add_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, str(condition))
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c145b2c3d512"
    assert migration["down_revision"] == "c144b2c3d511"
    added = [operation for operation in operations if operation[0] == "add_column"]
    assert [operation[2].name for operation in added] == [
        "redemption_price_type",
        "old_factor",
        "new_factor",
        "principal_proceeds_local",
        "accrued_interest_proceeds_local",
        "embedded_fee_amount_local",
        "embedded_tax_amount_local",
    ]
    assert all(isinstance(operation[2], Column) and operation[2].nullable for operation in added)
    assert all(isinstance(operation[2].type, Numeric) for operation in added[1:])
    constraints = {
        operation[1]: operation[3]
        for operation in operations
        if operation[0] == "create_check_constraint"
    }
    assert (
        "old_factor IS NOT NULL AND new_factor IS NOT NULL"
        in constraints["ck_transactions_redemption_factor_transition"]
    )
    assert "new_factor < old_factor" in constraints["ck_transactions_redemption_factor_transition"]
    assert (
        "principal_proceeds_local >= 0"
        in constraints["ck_transactions_redemption_amounts_nonnegative"]
    )
    assert "CAST(old_factor AS TEXT)" in constraints["ck_transactions_redemption_values_finite"]
    assert [operation[2] for operation in operations if operation[0] == "drop_column"] == [
        "embedded_tax_amount_local",
        "embedded_fee_amount_local",
        "accrued_interest_proceeds_local",
        "principal_proceeds_local",
        "new_factor",
        "old_factor",
        "redemption_price_type",
    ]
