"""Executable contract for persisted valuation FX effective-date lineage."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from portfolio_common.database_models import DailyPositionSnapshot
from portfolio_common.financial_numeric import ExactNumeric
from sqlalchemy import Column, Date, Numeric, String

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
    assert len(operations) == 14

    operation, table_name, definition = operations[0]
    assert operation == "add_column"
    assert table_name == "daily_position_snapshots"
    assert isinstance(definition, Column)
    assert definition.name == "valuation_source_currency"
    assert isinstance(definition.type, String)
    assert definition.type.length == 3
    assert definition.nullable is True
    assert definition.server_default is None

    operation, table_name, definition = operations[1]
    assert operation == "add_column"
    assert table_name == "daily_position_snapshots"
    assert isinstance(definition, Column)
    assert definition.name == "valuation_reporting_currency"
    assert isinstance(definition.type, String)
    assert definition.type.length == 3
    assert definition.nullable is True

    operation, table_name, definition = operations[2]
    assert operation == "add_column"
    assert table_name == "daily_position_snapshots"
    assert isinstance(definition, Column)
    assert definition.name == "valuation_fx_rate_date"
    assert isinstance(definition.type, Date)
    assert definition.nullable is True

    operation, table_name, definition = operations[3]
    assert operation == "add_column"
    assert table_name == "daily_position_snapshots"
    assert isinstance(definition, Column)
    assert definition.name == "valuation_fx_rate"
    assert isinstance(definition.type, Numeric)
    assert definition.type.precision == 18
    assert definition.type.scale == 10
    assert definition.nullable is True

    assert operations[4][:3] == (
        "create_check_constraint",
        "ck_daily_position_snapshot_valuation_fx_fact",
        "daily_position_snapshots",
    )
    constraint_sql = operations[4][3]
    assert "valuation_fx_rate_date IS NULL AND valuation_fx_rate IS NULL" in constraint_sql
    assert "valuation_fx_rate_date IS NOT NULL" in constraint_sql
    assert "valuation_fx_rate IS NOT NULL" in constraint_sql
    assert "valuation_source_currency IS NOT NULL" in constraint_sql
    assert "valuation_reporting_currency IS NOT NULL" in constraint_sql
    assert "valuation_source_currency <> valuation_reporting_currency" in constraint_sql
    assert "'NaN', 'Infinity', '-Infinity'" in constraint_sql

    assert operations[5][:3] == (
        "create_check_constraint",
        "ck_daily_snapshot_valuation_currency_pair",
        "daily_position_snapshots",
    )
    currency_constraint_sql = operations[5][3]
    assert "valuation_source_currency IS NULL" in currency_constraint_sql
    assert "valuation_reporting_currency IS NULL" in currency_constraint_sql
    assert "upper(btrim(valuation_source_currency))" in currency_constraint_sql
    assert "upper(btrim(valuation_reporting_currency))" in currency_constraint_sql

    assert operations[6] == (
        "create_check_constraint",
        "ck_daily_snapshot_fx_rate_positive",
        "daily_position_snapshots",
        "valuation_fx_rate > 0",
    )
    assert operations[7] == (
        "drop_constraint",
        "ck_daily_snapshot_valuation_currency_pair",
        "daily_position_snapshots",
        {"type_": "check"},
    )
    assert operations[8] == (
        "drop_constraint",
        "ck_daily_snapshot_fx_rate_positive",
        "daily_position_snapshots",
        {"type_": "check"},
    )
    assert operations[9] == (
        "drop_constraint",
        "ck_daily_position_snapshot_valuation_fx_fact",
        "daily_position_snapshots",
        {"type_": "check"},
    )
    assert operations[10] == (
        "drop_column",
        "daily_position_snapshots",
        "valuation_fx_rate",
    )
    assert operations[11] == (
        "drop_column",
        "daily_position_snapshots",
        "valuation_fx_rate_date",
    )
    assert operations[12] == (
        "drop_column",
        "daily_position_snapshots",
        "valuation_reporting_currency",
    )
    assert operations[13] == (
        "drop_column",
        "daily_position_snapshots",
        "valuation_source_currency",
    )

    orm_column = DailyPositionSnapshot.__table__.c.valuation_fx_rate_date
    assert isinstance(orm_column.type, Date)
    assert orm_column.nullable is True

    orm_rate_column = DailyPositionSnapshot.__table__.c.valuation_fx_rate
    assert isinstance(orm_rate_column.type, ExactNumeric)
    assert orm_rate_column.type.precision == 18
    assert orm_rate_column.type.scale == 10
    assert orm_rate_column.nullable is True

    orm_source_currency = DailyPositionSnapshot.__table__.c.valuation_source_currency
    assert isinstance(orm_source_currency.type, String)
    assert orm_source_currency.type.length == 3
    assert orm_source_currency.nullable is True

    orm_reporting_currency = DailyPositionSnapshot.__table__.c.valuation_reporting_currency
    assert isinstance(orm_reporting_currency.type, String)
    assert orm_reporting_currency.type.length == 3
    assert orm_reporting_currency.nullable is True

    orm_constraint = next(
        constraint
        for constraint in DailyPositionSnapshot.__table__.constraints
        if constraint.name == "ck_daily_position_snapshot_valuation_fx_fact"
    )
    assert str(orm_constraint.sqltext) == constraint_sql
    orm_currency_constraint = next(
        constraint
        for constraint in DailyPositionSnapshot.__table__.constraints
        if constraint.name == "ck_daily_snapshot_valuation_currency_pair"
    )
    assert str(orm_currency_constraint.sqltext) == currency_constraint_sql
