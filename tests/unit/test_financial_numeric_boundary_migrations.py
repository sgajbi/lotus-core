"""Executable parity proof for the finite financial numeric migration chain."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from portfolio_common.database_models import Base

from alembic import op

MIGRATION_ROOT = Path(__file__).resolve().parents[2] / "alembic" / "versions"
MIGRATION_SPECS = (
    (
        "c122b2c3d4fb_fix_reference_numeric_boundaries.py",
        "c122b2c3d4fb",
        "c121b2c3d4fa",
        {
            "fx_rates",
            "market_prices",
            "instruments",
            "benchmark_composition_series",
            "index_price_series",
            "index_return_series",
            "benchmark_return_series",
            "risk_free_series",
            "instrument_lookthrough_components",
        },
    ),
    (
        "c123b2c3d4fc_fix_client_policy_numeric_boundaries.py",
        "c123b2c3d4fc",
        "c122b2c3d4fb",
        {
            "sustainability_preference_profiles",
            "client_tax_profiles",
            "client_tax_rule_sets",
            "client_income_needs_schedules",
            "liquidity_reserve_requirements",
            "planned_withdrawal_schedules",
            "model_portfolio_targets",
        },
    ),
    (
        "c124b2c3d4fd_fix_position_state_numeric_boundaries.py",
        "c124b2c3d4fd",
        "c123b2c3d4fc",
        {
            "simulation_changes",
            "position_history",
            "daily_position_snapshots",
        },
    ),
    (
        "c125b2c3d4fe_fix_transaction_numeric_boundaries.py",
        "c125b2c3d4fe",
        "c124b2c3d4fd",
        {"transactions", "cashflows"},
    ),
    (
        "c126b2c3d4ff_fix_timeseries_numeric_boundaries.py",
        "c126b2c3d4ff",
        "c125b2c3d4fe",
        {
            "position_timeseries",
            "portfolio_timeseries",
            "financial_reconciliation_runs",
        },
    ),
)


@pytest.mark.parametrize(
    ("filename", "revision", "down_revision", "expected_tables"),
    MIGRATION_SPECS,
)
def test_financial_numeric_migration_is_bounded_reversible_and_matches_orm(
    monkeypatch,
    filename: str,
    revision: str,
    down_revision: str,
    expected_tables: set[str],
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition, **kwargs: operations.append(
            ("create", table, name, condition, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "execute",
        lambda statement: operations.append(("execute", statement)),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop", table, name, kwargs)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION_ROOT / filename))
    migration["upgrade"]()
    migration["downgrade"]()

    constraints = migration["_CONSTRAINTS"]
    creates = [operation for operation in operations if operation[0] == "create"]
    validates = [operation for operation in operations if operation[0] == "execute"]
    drops = [operation for operation in operations if operation[0] == "drop"]

    assert migration["revision"] == revision
    assert migration["down_revision"] == down_revision
    assert {table_name for table_name, _, _ in constraints} == expected_tables
    assert [(operation[1], operation[2], operation[3]) for operation in creates] == list(
        constraints
    )
    assert all(operation[4] == {"postgresql_not_valid": True} for operation in creates)
    assert len(validates) == len(expected_tables)
    for table_name in expected_tables:
        table_validations = [
            str(operation[1])
            for operation in validates
            if str(operation[1]).startswith(f'ALTER TABLE "{table_name}" ')
        ]
        assert len(table_validations) == 1
        statement = table_validations[0]
        expected_names = {
            constraint_name
            for constraint_table, constraint_name, _ in constraints
            if constraint_table == table_name
        }
        assert all(
            statement.count(f'VALIDATE CONSTRAINT "{constraint_name}"') == 1
            for constraint_name in expected_names
        )

    assert [(operation[1], operation[2]) for operation in drops] == [
        (table_name, constraint_name) for table_name, constraint_name, _ in reversed(constraints)
    ]
    assert all(operation[3] == {"type_": "check"} for operation in drops)

    for table_name, constraint_name, condition in constraints:
        orm_constraints = {
            constraint.name: constraint
            for constraint in Base.metadata.tables[table_name].constraints
            if constraint.name is not None
        }
        assert str(orm_constraints[constraint_name].sqltext) == condition
