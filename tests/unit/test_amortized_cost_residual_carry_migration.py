"""Executable migration contract for amortized-cost residual carry state."""

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
    / "c143b2c3d510_fix_conserve_amortized_cost_residual.py"
)


def test_residual_carry_migration_is_additive_and_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(("add_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, condition)
        ),
    )
    monkeypatch.setattr(
        op,
        "create_foreign_key",
        lambda name, source, target, local, remote, **kwargs: operations.append(
            (
                "create_foreign_key",
                name,
                source,
                target,
                tuple(local),
                tuple(remote),
                kwargs,
            )
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c143b2c3d510"
    assert migration["down_revision"] == "c142b2c3d50f"

    added = [operation for operation in operations if operation[0] == "add_column"]
    assert [(operation[1], operation[2].name) for operation in added] == [
        ("position_lot_state", "amortized_cost_profile_id"),
        ("position_lot_state", "amortized_cost_profile_version"),
        ("position_lot_state", "amortized_cost_profile_content_hash"),
        ("position_lot_state", "amortized_cost_recognized_through"),
        ("position_lot_state", "amortized_cost_scheduled_local"),
        ("position_lot_state", "amortized_cost_book_fx_rate_to_base"),
        ("lot_disposal_allocations", "amortized_cost_scheduled_local"),
        ("lot_disposal_allocations", "amortized_cost_current_base"),
        ("lot_disposal_allocations", "amortized_cost_retained_rounding_local"),
        ("lot_disposal_allocations", "amortized_cost_retained_rounding_base"),
    ]
    assert all(isinstance(operation[2], Column) and operation[2].nullable for operation in added)

    foreign_key = next(
        operation for operation in operations if operation[0] == "create_foreign_key"
    )
    assert foreign_key[1:] == (
        "fk_position_lot_amortized_cost_profile",
        "position_lot_state",
        "lot_amortized_cost_profiles",
        (
            "amortized_cost_profile_id",
            "amortized_cost_profile_version",
            "lot_id",
            "portfolio_id",
            "security_id",
        ),
        ("profile_id", "profile_version", "lot_id", "portfolio_id", "security_id"),
        {"ondelete": "RESTRICT"},
    )

    check_conditions = [
        str(operation[3]) for operation in operations if operation[0] == "create_check_constraint"
    ]
    assert any("amortized_cost_current_base IS NOT NULL" in item for item in check_conditions)
    assert any("amortized_cost_retained_rounding_local" in item for item in check_conditions)

    dropped = [operation for operation in operations if operation[0] == "drop_column"]
    assert [(operation[1], operation[2]) for operation in dropped] == [
        ("lot_disposal_allocations", "amortized_cost_retained_rounding_base"),
        ("lot_disposal_allocations", "amortized_cost_retained_rounding_local"),
        ("lot_disposal_allocations", "amortized_cost_current_base"),
        ("lot_disposal_allocations", "amortized_cost_scheduled_local"),
        ("position_lot_state", "amortized_cost_book_fx_rate_to_base"),
        ("position_lot_state", "amortized_cost_scheduled_local"),
        ("position_lot_state", "amortized_cost_recognized_through"),
        ("position_lot_state", "amortized_cost_profile_content_hash"),
        ("position_lot_state", "amortized_cost_profile_version"),
        ("position_lot_state", "amortized_cost_profile_id"),
    ]
