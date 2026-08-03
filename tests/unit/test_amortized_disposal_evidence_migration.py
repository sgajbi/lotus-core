"""Executable migration contract for amortized disposal-allocation evidence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c142b2c3d50f_feat_add_amortized_disposal_evidence.py"
)


def test_amortized_disposal_evidence_migration_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "create_unique_constraint",
        lambda name, table, columns: operations.append(
            ("create_unique_constraint", name, table, tuple(columns))
        ),
    )
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

    assert migration["revision"] == "c142b2c3d50f"
    assert migration["down_revision"] == "c141b2c3d50e"

    added = [operation[2] for operation in operations if operation[0] == "add_column"]
    assert all(isinstance(column, Column) and column.nullable for column in added)
    assert [column.name for column in added] == [
        "amortized_cost_profile_id",
        "amortized_cost_profile_version",
        "amortized_cost_profile_content_hash",
        "amortized_cost_currency",
        "amortized_cost_recognized_through",
        "amortized_cost_original_quantity",
        "amortized_cost_open_quantity_before",
        "amortized_cost_residual_quantity",
        "amortized_cost_current_local",
        "amortized_cost_residual_local",
        "amortized_cost_book_fx_rate_to_base",
        "amortized_cost_residual_base",
        "amortized_cost_calculation_lineage",
    ]
    assert isinstance(added[-1].type, JSONB)

    created_constraints = {
        str(operation[1])
        for operation in operations
        if operation[0]
        in {"create_unique_constraint", "create_check_constraint", "create_foreign_key"}
    }
    assert created_constraints == {
        "uq_lot_amort_profile_allocation_scope",
        "ck_lot_disposal_allocation_amort_shape",
        "ck_lot_disposal_allocation_amort_values",
        "ck_lot_disposal_allocation_amort_finite",
        "fk_lot_disposal_allocation_amort_profile",
    }

    foreign_key = next(
        operation for operation in operations if operation[0] == "create_foreign_key"
    )
    assert foreign_key[4] == (
        "amortized_cost_profile_id",
        "amortized_cost_profile_version",
        "source_lot_id",
        "portfolio_id",
        "security_id",
    )
    assert foreign_key[5] == (
        "profile_id",
        "profile_version",
        "lot_id",
        "portfolio_id",
        "security_id",
    )
    assert foreign_key[6] == {"ondelete": "RESTRICT"}

    dropped_columns = [operation[2] for operation in operations if operation[0] == "drop_column"]
    assert dropped_columns == list(reversed([column.name for column in added]))
    drop_names = [operation[1] for operation in operations if operation[0] == "drop_constraint"]
    assert drop_names[0] == "fk_lot_disposal_allocation_amort_profile"
    assert drop_names[-1] == "uq_lot_amort_profile_allocation_scope"
