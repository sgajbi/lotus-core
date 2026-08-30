"""Executable contract for durable simulation-session tenant ownership."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c166b2c3d52d_fix_bind_simulation_session_tenant.py"
)


def test_simulation_session_tenant_migration_is_fail_closed_and_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(
            ("add_column", table, column.name, column.nullable)
        ),
    )
    monkeypatch.setattr(
        op,
        "execute",
        lambda statement: operations.append(("execute", str(statement))),
    )
    monkeypatch.setattr(
        op,
        "alter_column",
        lambda table, column, **kwargs: operations.append(("alter_column", table, column, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(("create_check", name, table, condition)),
    )
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns, **kwargs: operations.append(
            ("create_index", name, table, tuple(columns), kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "create_unique_constraint",
        lambda name, table, columns: operations.append(
            ("create_unique", name, table, tuple(columns))
        ),
    )
    monkeypatch.setattr(
        op,
        "create_foreign_key",
        lambda name, source, target, local, remote: operations.append(
            ("create_fk", name, source, target, tuple(local), tuple(remote))
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
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

    assert migration["revision"] == "c166b2c3d52d"
    assert migration["down_revision"] == "c165b2c3d52c"
    assert operations[0] == ("add_column", "simulation_sessions", "tenant_id", True)
    backfill = operations[1][1]
    assert "SET tenant_id = portfolio.tenant_id" in backfill
    assert "session.portfolio_id = portfolio.portfolio_id" in backfill
    assert "RAISE EXCEPTION" in backfill
    assert "do not assign a synthetic or deployment-default tenant" in backfill
    assert operations[2][0:3] == (
        "alter_column",
        "simulation_sessions",
        "tenant_id",
    )
    assert operations[2][3]["nullable"] is False
    assert operations[3][0:3] == (
        "create_check",
        "ck_simulation_sessions_tenant_authority",
        "simulation_sessions",
    )
    assert (
        "create_index",
        "ix_simulation_sessions_tenant_session_id",
        "simulation_sessions",
        ("tenant_id", "session_id"),
        {},
    ) in operations
    assert (
        "create_unique",
        "uq_portfolios_tenant_portfolio_id",
        "portfolios",
        ("tenant_id", "portfolio_id"),
    ) in operations
    assert (
        "create_fk",
        "fk_simulation_sessions_tenant_portfolio",
        "simulation_sessions",
        "portfolios",
        ("tenant_id", "portfolio_id"),
        ("tenant_id", "portfolio_id"),
    ) in operations
    assert (
        "drop_constraint",
        "simulation_sessions_portfolio_id_fkey",
        "simulation_sessions",
        {"type_": "foreignkey"},
    ) in operations
    assert operations[-8:] == [
        (
            "drop_index",
            "ix_simulation_sessions_tenant_session_id",
            {"table_name": "simulation_sessions"},
        ),
        (
            "drop_index",
            "ix_simulation_sessions_tenant_id",
            {"table_name": "simulation_sessions"},
        ),
        (
            "drop_constraint",
            "fk_simulation_sessions_tenant_portfolio",
            "simulation_sessions",
            {"type_": "foreignkey"},
        ),
        (
            "create_fk",
            "simulation_sessions_portfolio_id_fkey",
            "simulation_sessions",
            "portfolios",
            ("portfolio_id",),
            ("portfolio_id",),
        ),
        (
            "drop_constraint",
            "uq_portfolios_tenant_portfolio_id",
            "portfolios",
            {"type_": "unique"},
        ),
        (
            "create_index",
            "ix_portfolios_tenant_portfolio_id",
            "portfolios",
            ("tenant_id", "portfolio_id"),
            {},
        ),
        (
            "drop_constraint",
            "ck_simulation_sessions_tenant_authority",
            "simulation_sessions",
            {"type_": "check"},
        ),
        ("drop_column", "simulation_sessions", "tenant_id"),
    ]
