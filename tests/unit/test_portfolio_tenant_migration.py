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
    preflights = [operation[1] for operation in operations if operation[0] == "execute"]
    preflight = preflights[0]
    assert "LOCK TABLE portfolios IN ACCESS EXCLUSIVE MODE" in preflight
    assert "SET tenant_id = btrim(tenant_id, U&' " in preflight
    assert "\\0009\\000A\\000B\\000C\\000D" in preflight
    assert "tenant_id IS NULL" in preflight
    assert "char_length(btrim(tenant_id, U&' " in preflight
    assert "RAISE EXCEPTION USING" in preflight
    assert preflight.index("RAISE EXCEPTION USING") < preflight.index("UPDATE portfolios")
    assert "do not assign a synthetic or deployment-default tenant" in preflight
    assert "ingestion job tenant cutover found %s unattributable row(s)" in preflights[1]
    assert "enterprise_security_audit_events" in preflights[1]
    assert "audit.component = 'ingestion_service'" in preflights[1]
    assert "audit.route_template = job.endpoint" in preflights[1]
    assert "audit.method = 'POST'" in preflights[1]
    assert "audit.decision = 'ALLOW'" in preflights[1]
    assert "audit.reason = 'authorized'" in preflights[1]
    assert "audit.correlation_id = job.correlation_id" in preflights[1]
    assert "audit.trace_id = job.trace_id" in preflights[1]
    assert "audit.occurred_at <= job.submitted_at" in preflights[1]
    assert "audit.occurred_at >= job.submitted_at - INTERVAL '5 minutes'" in preflights[1]
    assert "HAVING count(*) = 1" in preflights[1]
    assert "do not assign a synthetic or deployment-default tenant" in preflights[1]
    assert "portfolio tenant downgrade found %s row(s) without legal-book scope" in preflights[2]
    assert "rollback will not fabricate accounting scope" in preflights[2]

    alterations = [operation for operation in operations if operation[0] == "alter_column"]
    assert alterations[0][3]["nullable"] is False
    assert alterations[1][1:3] == ("ingestion_jobs", "tenant_id")
    assert alterations[1][3]["nullable"] is False
    assert alterations[2][3]["nullable"] is True
    assert operations.index(("execute", preflight)) < next(
        index for index, operation in enumerate(operations) if operation[0] == "alter_column"
    )
    assert operations.index(("execute", preflights[2])) < next(
        index
        for index, operation in enumerate(operations)
        if operation[0] == "drop_index" and operation[1] == "ix_portfolios_tenant_portfolio_id"
    )

    checks = [operation for operation in operations if operation[0] == "create_check"]
    assert "legal_book_id IS NULL OR" in checks[0][3]
    assert "tenant_id = btrim(tenant_id, U&' " in checks[0][3]
    assert checks[1][1:3] == ("ck_ingestion_jobs_tenant_authority", "ingestion_jobs")
    assert "tenant_id = btrim(tenant_id, U&' " in checks[1][3]
    assert "char_length(tenant_id) <= 128" in checks[1][3]
    assert "tenant_id IS NULL AND legal_book_id IS NULL" in checks[2][3]
    assert (
        "create_index",
        "ix_portfolios_tenant_portfolio_id",
        "portfolios",
        ["tenant_id", "portfolio_id"],
    ) in operations
    assert any(
        operation[0] == "create_index"
        and operation[1] == "ix_ingestion_jobs_tenant_endpoint_idempotency_submitted"
        and operation[2] == "ingestion_jobs"
        and operation[3][:3] == ["tenant_id", "endpoint", "idempotency_key"]
        for operation in operations
    )
    assert any(
        operation[0] == "add_column"
        and operation[1] == "ingestion_jobs"
        and operation[2].name == "tenant_id"
        for operation in operations
    )
    assert ("drop_column", "ingestion_jobs", "tenant_id") in operations
