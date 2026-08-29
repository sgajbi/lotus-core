"""Executable contract for persisted valuation FX effective-date lineage."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from portfolio_common.database_models import DailyPositionSnapshot
from portfolio_common.financial_numeric import ExactNumeric
from sqlalchemy import Column, Date, Numeric

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
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, condition)
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

    assert migration["revision"] == "c163b2c3d52a"
    assert migration["down_revision"] == "c162b2c3d529"
    assert len(operations) == 8

    operation, table_name, definition = operations[0]
    assert operation == "add_column"
    assert table_name == "daily_position_snapshots"
    assert isinstance(definition, Column)
    assert definition.name == "valuation_fx_rate_date"
    assert isinstance(definition.type, Date)
    assert definition.nullable is True
    assert definition.server_default is None

    operation, table_name, definition = operations[1]
    assert operation == "add_column"
    assert table_name == "daily_position_snapshots"
    assert isinstance(definition, Column)
    assert definition.name == "valuation_fx_rate"
    assert isinstance(definition.type, Numeric)
    assert definition.type.precision == 18
    assert definition.type.scale == 10
    assert definition.nullable is True

    assert operations[2][:3] == (
        "create_check_constraint",
        "ck_daily_position_snapshot_valuation_fx_fact",
        "daily_position_snapshots",
    )
    constraint_sql = operations[2][3]
    assert "valuation_fx_rate_date IS NULL AND valuation_fx_rate IS NULL" in constraint_sql
    assert "valuation_fx_rate_date IS NOT NULL" in constraint_sql
    assert "valuation_fx_rate IS NOT NULL" in constraint_sql
    assert "'NaN', 'Infinity', '-Infinity'" in constraint_sql

    assert operations[3] == (
        "create_check_constraint",
        "ck_daily_snapshot_fx_rate_positive",
        "daily_position_snapshots",
        "valuation_fx_rate > 0",
    )
    assert operations[4] == (
        "drop_constraint",
        "ck_daily_snapshot_fx_rate_positive",
        "daily_position_snapshots",
        {"type_": "check"},
    )
    assert operations[5] == (
        "drop_constraint",
        "ck_daily_position_snapshot_valuation_fx_fact",
        "daily_position_snapshots",
        {"type_": "check"},
    )
    assert operations[6] == (
        "drop_column",
        "daily_position_snapshots",
        "valuation_fx_rate",
    )
    assert operations[7] == (
        "drop_column",
        "daily_position_snapshots",
        "valuation_fx_rate_date",
    )

    orm_column = DailyPositionSnapshot.__table__.c.valuation_fx_rate_date
    assert isinstance(orm_column.type, Date)
    assert orm_column.nullable is True

    orm_rate_column = DailyPositionSnapshot.__table__.c.valuation_fx_rate
    assert isinstance(orm_rate_column.type, ExactNumeric)
    assert orm_rate_column.type.precision == 18
    assert orm_rate_column.type.scale == 10
    assert orm_rate_column.nullable is True

    orm_constraint = next(
        constraint
        for constraint in DailyPositionSnapshot.__table__.constraints
        if constraint.name == "ck_daily_position_snapshot_valuation_fx_fact"
    )
    assert str(orm_constraint.sqltext) == constraint_sql
