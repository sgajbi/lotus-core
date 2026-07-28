"""PostgreSQL lifecycle proof for the complete finite numeric boundary chain."""

from __future__ import annotations

import json
import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import Base
from sqlalchemy import Numeric, text
from sqlalchemy.exc import DatabaseError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATHS = tuple(
    ROOT / "alembic" / "versions" / filename
    for filename in (
        "c122b2c3d4fb_fix_reference_numeric_boundaries.py",
        "c123b2c3d4fc_fix_client_policy_numeric_boundaries.py",
        "c124b2c3d4fd_fix_position_state_numeric_boundaries.py",
        "c125b2c3d4fe_fix_transaction_numeric_boundaries.py",
        "c126b2c3d4ff_fix_timeseries_numeric_boundaries.py",
    )
)
CONTRACT_PATH = ROOT / "docs" / "standards" / "financial-numeric-persistence.v1.json"
SPECIAL_VALUES = ("NaN", "Infinity", "-Infinity")


def _load_migrations() -> tuple[dict[str, Any], ...]:
    return tuple(runpy.run_path(str(path)) for path in MIGRATION_PATHS)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _governed_columns(
    migrations: tuple[dict[str, Any], ...],
) -> dict[str, tuple[str, ...]]:
    governed: dict[str, list[str]] = {}
    conditions_by_table: dict[str, list[str]] = {}
    for migration in migrations:
        for table_name, _, condition in migration["_CONSTRAINTS"]:
            conditions_by_table.setdefault(table_name, []).append(condition)
    for table_name, conditions in conditions_by_table.items():
        combined = " ".join(conditions)
        numeric_columns = (
            column
            for column in Base.metadata.tables[table_name].columns
            if isinstance(column.type, Numeric)
        )
        for column in numeric_columns:
            finite_term = f"CAST({column.name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
            if finite_term in combined:
                governed.setdefault(table_name, []).append(column.name)
    result = {table_name: tuple(column_names) for table_name, column_names in governed.items()}
    assert sum(len(column_names) for column_names in result.values()) == 82
    return result


def _profiles() -> dict[str, dict[str, object]]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return {
        f"{table_name}.{column_name}": classification
        for table_name, columns in contract["tables"].items()
        for column_name, classification in columns.items()
    }


def _create_temporary_tables(
    connection,
    governed_columns: dict[str, tuple[str, ...]],
) -> None:
    quote = connection.dialect.identifier_preparer.quote
    for table_name, column_names in governed_columns.items():
        model_table = Base.metadata.tables[table_name]
        declarations = ["row_id INTEGER PRIMARY KEY"]
        for column_name in column_names:
            column = model_table.c[column_name]
            type_sql = column.type.compile(dialect=connection.dialect)
            nullable_sql = "" if column.nullable else " NOT NULL"
            declarations.append(f"{quote(column_name)} {type_sql}{nullable_sql}")
        connection.execute(
            text(
                f"CREATE TEMP TABLE {quote(table_name)} ({', '.join(declarations)}) ON COMMIT DROP"
            )
        )
        quoted_columns = ", ".join(quote(column_name) for column_name in column_names)
        value_names = ", ".join(f":value_{index}" for index, _ in enumerate(column_names))
        values = {f"value_{index}": Decimal("1") for index, _ in enumerate(column_names)}
        connection.execute(
            text(
                f"INSERT INTO {quote(table_name)} "
                f"(row_id, {quoted_columns}) VALUES (1, {value_names})"
            ),
            values,
        )


def _constraint_state(
    connection,
    constraint_names: set[str],
) -> dict[tuple[str, str], bool]:
    rows = connection.execute(
        text(
            """
            SELECT relation.relname, constraint_record.conname,
                   constraint_record.convalidated
            FROM pg_constraint AS constraint_record
            JOIN pg_class AS relation
              ON relation.oid = constraint_record.conrelid
            WHERE relation.relnamespace = pg_my_temp_schema()
              AND constraint_record.conname = ANY(CAST(:names AS text[]))
            """
        ),
        {"names": sorted(constraint_names)},
    )
    return {
        (table_name, constraint_name): validated for table_name, constraint_name, validated in rows
    }


def _set_value(connection, table_name: str, column_name: str, value: str) -> None:
    quote = connection.dialect.identifier_preparer.quote
    connection.execute(
        text(
            f"UPDATE {quote(table_name)} "
            f"SET {quote(column_name)} = CAST(:value AS NUMERIC) "
            "WHERE row_id = 1"
        ),
        {"value": value},
    )


def _assert_rejected(
    connection,
    table_name: str,
    column_name: str,
    value: str,
) -> None:
    savepoint = connection.begin_nested()
    with pytest.raises(DatabaseError):
        _set_value(connection, table_name, column_name, value)
    savepoint.rollback()


def _assert_accepted(
    connection,
    table_name: str,
    column_name: str,
    value: str,
) -> None:
    quote = connection.dialect.identifier_preparer.quote
    savepoint = connection.begin_nested()
    _set_value(connection, table_name, column_name, value)
    persisted = connection.execute(
        text(f"SELECT {quote(column_name)} FROM {quote(table_name)} WHERE row_id = 1")
    ).scalar_one()
    assert persisted == Decimal(value)
    savepoint.rollback()


def _assert_nullability(
    connection,
    table_name: str,
    column_name: str,
    *,
    nullable: bool,
) -> None:
    quote = connection.dialect.identifier_preparer.quote
    statement = text(f"UPDATE {quote(table_name)} SET {quote(column_name)} = NULL WHERE row_id = 1")
    savepoint = connection.begin_nested()
    if nullable:
        result = connection.execute(statement)
        assert result.rowcount == 1
    else:
        with pytest.raises(DatabaseError):
            connection.execute(statement)
    savepoint.rollback()


def _typmod_boundary(numeric_type: Numeric) -> str:
    assert numeric_type.precision is not None
    assert numeric_type.scale is not None
    integer_digits = numeric_type.precision - numeric_type.scale
    return f"{'9' * integer_digits}.{'9' * numeric_type.scale}"


def test_financial_numeric_boundary_migrations_reject_special_values_and_preserve_contracts(
    db_engine,
    clean_db,
) -> None:
    migrations = _load_migrations()
    governed_columns = _governed_columns(migrations)
    profiles = _profiles()
    expected_constraints = {
        (table_name, constraint_name)
        for migration in migrations
        for table_name, constraint_name, _ in migration["_CONSTRAINTS"]
    }
    expected_names = {constraint_name for _, constraint_name in expected_constraints}

    with db_engine.begin() as connection:
        _create_temporary_tables(connection, governed_columns)
        for migration in migrations:
            _bind_operations(migration, connection)

        assert _constraint_state(connection, expected_names) == {}

        _set_value(connection, "fx_rates", "rate", "NaN")
        failed_upgrade = connection.begin_nested()
        with pytest.raises(DatabaseError):
            migrations[0]["upgrade"]()
        failed_upgrade.rollback()
        assert _constraint_state(connection, expected_names) == {}
        _set_value(connection, "fx_rates", "rate", "1")

        for migration in migrations:
            migration["upgrade"]()

        constraint_state = _constraint_state(connection, expected_names)
        assert set(constraint_state) == expected_constraints
        assert all(constraint_state.values())

        for table_name, column_names in governed_columns.items():
            model_table = Base.metadata.tables[table_name]
            for column_name in column_names:
                identity = f"{table_name}.{column_name}"
                classification = profiles[identity]
                assert classification["rollout_status"] == "orm-enforced"
                profile = str(classification["profile"])
                sign = (
                    "positive"
                    if "positive" in profile and "nonnegative" not in profile
                    else "nonnegative"
                    if "nonnegative" in profile
                    else "signed"
                )

                for special_value in SPECIAL_VALUES:
                    _assert_rejected(
                        connection,
                        table_name,
                        column_name,
                        special_value,
                    )
                if sign == "positive":
                    _assert_rejected(connection, table_name, column_name, "0")
                    _assert_rejected(connection, table_name, column_name, "-1")
                    _assert_accepted(connection, table_name, column_name, "1")
                elif sign == "nonnegative":
                    _assert_rejected(connection, table_name, column_name, "-1")
                    _assert_accepted(connection, table_name, column_name, "0")
                else:
                    _assert_accepted(connection, table_name, column_name, "-1")
                    _assert_accepted(connection, table_name, column_name, "0")

                column = model_table.c[column_name]
                _assert_accepted(
                    connection,
                    table_name,
                    column_name,
                    _typmod_boundary(column.type),
                )
                _assert_nullability(
                    connection,
                    table_name,
                    column_name,
                    nullable=column.nullable,
                )

        for migration in reversed(migrations):
            migration["downgrade"]()
        assert _constraint_state(connection, expected_names) == {}

        for migration in migrations:
            migration["upgrade"]()
        reapplied = _constraint_state(connection, expected_names)
        assert set(reapplied) == expected_constraints
        assert all(reapplied.values())
