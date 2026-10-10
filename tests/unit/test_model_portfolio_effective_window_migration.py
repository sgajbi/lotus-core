"""Operation ordering complements the real PostgreSQL retained-row proof."""

import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/c184b2c3d545_model_portfolio_effective_windows.py"
)
TABLES = ("model_portfolio_definitions", "model_portfolio_targets")
NAMES = (
    "ck_model_portfolio_definition_effective_window",
    "ck_model_portfolio_target_effective_window",
)


@pytest.fixture
def migration_operations(monkeypatch):
    operations = Mock()
    for name in ("execute", "create_check_constraint", "drop_constraint"):
        monkeypatch.setattr(op, name, getattr(operations, name))
    return runpy.run_path(str(MIGRATION)), operations


def test_upgrade_fences_and_preflights_both_tables_before_installing_checks(migration_operations):
    migration, operations = migration_operations
    migration["upgrade"]()
    calls = operations.mock_calls
    assert [item[0] for item in calls] == ["execute"] * 4 + ["create_check_constraint"] * 2
    assert str(calls[0].args[0]) == "SET LOCAL lock_timeout = '5s'"
    assert str(calls[1].args[0]) == (
        "LOCK TABLE model_portfolio_definitions, model_portfolio_targets IN ACCESS EXCLUSIVE MODE"
    )
    for item, table in zip(calls[2:4], TABLES, strict=True):
        sql = str(item.args[0])
        assert f"SELECT 1 FROM {table} WHERE effective_to < effective_from" in sql
        assert f"MODEL_PORTFOLIO_INVALID_EFFECTIVE_WINDOW: {table}" in sql
        assert "retain rows and resolve source evidence before retry" in sql
    for item, table, name in zip(calls[4:], TABLES, NAMES, strict=True):
        assert item.args == (name, table, "effective_to IS NULL OR effective_to >= effective_from")
    assert migration["down_revision"] == "c183b2c3d544"


@pytest.mark.parametrize("invalid_table", TABLES)
def test_preflight_failure_propagates_before_any_constraint_installation(
    migration_operations, invalid_table
):
    migration, operations = migration_operations

    def refuse_retained_invalid_rows(statement):
        if f"SELECT 1 FROM {invalid_table} " in str(statement):
            raise RuntimeError("retained invalid source evidence")

    operations.execute.side_effect = refuse_retained_invalid_rows
    with pytest.raises(RuntimeError, match="retained invalid source evidence"):
        migration["upgrade"]()
    operations.create_check_constraint.assert_not_called()
    operations.drop_constraint.assert_not_called()
    assert "ACCESS EXCLUSIVE MODE" in str(operations.execute.call_args_list[1].args[0])


def test_downgrade_only_removes_owned_checks_in_reverse_order(migration_operations):
    migration, operations = migration_operations
    migration["downgrade"]()
    assert [item[0] for item in operations.mock_calls] == ["drop_constraint"] * 2
    for item, table, name in zip(
        operations.mock_calls, reversed(TABLES), reversed(NAMES), strict=True
    ):
        assert item.args == (name, table)
        assert item.kwargs == {"type_": "check"}
