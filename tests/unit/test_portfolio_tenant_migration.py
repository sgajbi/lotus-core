"""Executable contract for the fail-closed portfolio tenant cutover."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c165b2c3d52c_fix_require_portfolio_tenant.py"
)


def test_portfolio_tenant_migration_fails_closed_and_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "execute",
        lambda statement: operations.append(("execute", str(statement))),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
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
        lambda name, table, columns: operations.append(("create_index", name, table, columns)),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c165b2c3d52c"
    assert migration["down_revision"] == "c163b2c3d52a"
    preflight = next(operation[1] for operation in operations if operation[0] == "execute")
    assert "LOCK TABLE portfolios IN ACCESS EXCLUSIVE MODE" in preflight
    assert "SET tenant_id = btrim(tenant_id)" in preflight
    assert "tenant_id IS NULL" in preflight
    assert "char_length(tenant_id) > 128" in preflight
    assert "RAISE EXCEPTION USING" in preflight
    assert "do not assign a synthetic or deployment-default tenant" in preflight

    alterations = [operation for operation in operations if operation[0] == "alter_column"]
    assert alterations[0][3]["nullable"] is False
    assert alterations[1][3]["nullable"] is True
    assert operations.index(("execute", preflight)) < next(
        index for index, operation in enumerate(operations) if operation[0] == "alter_column"
    )

    checks = [operation for operation in operations if operation[0] == "create_check"]
    assert "legal_book_id IS NULL OR" in checks[0][3]
    assert "tenant_id IS NULL AND legal_book_id IS NULL" in checks[1][3]
    assert (
        "create_index",
        "ix_portfolios_tenant_portfolio_id",
        "portfolios",
        ["tenant_id", "portfolio_id"],
    ) in operations
