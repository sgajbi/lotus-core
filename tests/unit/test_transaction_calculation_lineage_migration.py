"""Executable contract proof for additive transaction calculation lineage."""

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
    / "c135b2c3d508_feat_add_transaction_calculation_lineage.py"
)


def test_transaction_calculation_lineage_migration_is_additive_and_reversible(
    monkeypatch,
) -> None:
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

    assert migration["revision"] == "c135b2c3d508"
    assert migration["down_revision"] == "c134b2c3d507"
    assert len(operations) == 2
    _, table_name, definition = operations[0]
    assert table_name == "transactions"
    assert isinstance(definition, Column)
    assert definition.name == "calculation_lineage"
    assert isinstance(definition.type, JSON)
    assert definition.type.none_as_null is True
    assert definition.nullable is True
    assert operations[1] == ("drop_column", "transactions", "calculation_lineage")
