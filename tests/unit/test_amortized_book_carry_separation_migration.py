"""Executable migration contract for independent amortized book carrying amounts."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import Column

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c144b2c3d511_fix_separate_amortized_book_carry.py"
)


def test_book_carry_migration_is_additive_backfilled_and_reversible(monkeypatch) -> None:
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
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, str(condition))
        ),
    )
    monkeypatch.setattr(op, "execute", lambda statement: operations.append(("execute", statement)))

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c144b2c3d511"
    assert migration["down_revision"] == "c143b2c3d510"
    added = [operation for operation in operations if operation[0] == "add_column"]
    assert [(operation[1], operation[2].name) for operation in added] == [
        ("position_lot_state", "amortized_book_carrying_local"),
        ("position_lot_state", "amortized_book_carrying_base"),
    ]
    assert all(isinstance(operation[2], Column) and operation[2].nullable for operation in added)
    statements = [operation[1] for operation in operations if operation[0] == "execute"]
    assert len(statements) == 2
    backfill, rollback_restore = statements
    assert "amortized_book_carrying_local = lot_cost_local" in backfill
    assert "amortized_book_carrying_base = lot_cost_base" in backfill
    assert "WHERE amortized_cost_profile_id IS NOT NULL" in backfill
    assert "lot_cost_local = amortized_book_carrying_local" in rollback_restore
    assert "lot_cost_base = amortized_book_carrying_base" in rollback_restore
    assert "WHERE amortized_cost_profile_id IS NOT NULL" in rollback_restore

    upgraded_shape = next(
        operation[3]
        for operation in operations
        if operation[:3]
        == (
            "create_check_constraint",
            "ck_position_lot_amortized_cost_shape",
            "position_lot_state",
        )
        and "amortized_book_carrying_local" in operation[3]
    )
    for column_name in (
        "amortized_book_carrying_local",
        "amortized_book_carrying_base",
    ):
        assert f"{column_name} IS NULL" in upgraded_shape
        assert f"{column_name} IS NOT NULL" in upgraded_shape

    upgraded_values = next(
        operation[3]
        for operation in operations
        if operation[:3]
        == (
            "create_check_constraint",
            "ck_position_lot_amortized_cost_values",
            "position_lot_state",
        )
        and "amortized_book_carrying_local >= 0" in operation[3]
    )
    assert "CAST(amortized_book_carrying_base AS TEXT)" in upgraded_values
    assert [
        (operation[1], operation[2]) for operation in operations if operation[0] == "drop_column"
    ] == [
        ("position_lot_state", "amortized_book_carrying_base"),
        ("position_lot_state", "amortized_book_carrying_local"),
    ]
    restore_index = operations.index(("execute", rollback_restore))
    first_drop_index = next(
        index for index, operation in enumerate(operations) if operation[0] == "drop_column"
    )
    assert restore_index < first_drop_index
