"""Executable contract proof for additive position-timeseries lineage."""

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
    / "c136b2c3d509_feat_add_position_timeseries_lineage.py"
)


def test_position_timeseries_lineage_migration_is_additive_and_reversible(monkeypatch) -> None:
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

    assert migration["revision"] == "c136b2c3d509"
    assert migration["down_revision"] == "c135b2c3d508"
    _, table_name, definition = operations[0]
    assert table_name == "position_timeseries"
    assert isinstance(definition, Column)
    assert definition.name == "calculation_lineage"
    assert isinstance(definition.type, JSON)
    assert definition.type.none_as_null is True
    assert definition.nullable is True
    assert operations[1] == ("drop_column", "position_timeseries", "calculation_lineage")
