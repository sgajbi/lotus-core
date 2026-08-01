"""Executable contract proof for additive FIFO and AVCO state lineage."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Column

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c138b2c3d50b_feat_add_cost_basis_state_lineage.py"
)


def test_cost_basis_state_lineage_migration_is_additive_and_reversible(monkeypatch) -> None:
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
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c138b2c3d50b"
    assert migration["down_revision"] == "c137b2c3d50a"
    for operation, table_name in zip(
        operations[:2], ("position_lot_state", "average_cost_pool_state"), strict=True
    ):
        _, actual_table, definition = operation
        assert actual_table == table_name
        assert isinstance(definition, Column)
        assert definition.name == "calculation_lineage"
        assert isinstance(definition.type, JSON)
        assert definition.type.none_as_null is True
        assert definition.nullable is True
    assert operations[2:] == [
        ("drop_column", "average_cost_pool_state", "calculation_lineage"),
        ("drop_column", "position_lot_state", "calculation_lineage"),
    ]
