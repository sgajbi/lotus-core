"""Executable contract for persisted valuation FX effective-date lineage."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from portfolio_common.database_models import DailyPositionSnapshot
from sqlalchemy import Column, Date

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c163b2c3d52a_feat_add_valuation_fx_effective_date.py"
)


def test_valuation_fx_effective_date_migration_is_additive_reversible_and_matches_orm(
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

    assert migration["revision"] == "c163b2c3d52a"
    assert migration["down_revision"] == "c162b2c3d529"
    assert len(operations) == 2

    operation, table_name, definition = operations[0]
    assert operation == "add_column"
    assert table_name == "daily_position_snapshots"
    assert isinstance(definition, Column)
    assert definition.name == "valuation_fx_rate_date"
    assert isinstance(definition.type, Date)
    assert definition.nullable is True
    assert definition.server_default is None

    assert operations[1] == (
        "drop_column",
        "daily_position_snapshots",
        "valuation_fx_rate_date",
    )

    orm_column = DailyPositionSnapshot.__table__.c.valuation_fx_rate_date
    assert isinstance(orm_column.type, Date)
    assert orm_column.nullable is True
