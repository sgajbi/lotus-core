"""Executable contract for durable analytics-export tenant ownership."""

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
    / "c167b2c3d52e_fix_bind_analytics_export_job_tenant.py"
)


def test_analytics_export_tenant_migration_is_fail_closed_and_reversible(
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
            ("create_index", name, table, tuple(str(column) for column in columns), kwargs)
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

    assert migration["revision"] == "c167b2c3d52e"
    assert migration["down_revision"] == "c166b2c3d52d"
    assert operations[0] == ("add_column", "analytics_export_jobs", "tenant_id", True)
    backfill = operations[1][1]
    assert "SET tenant_id = portfolio.tenant_id" in backfill
    assert "job.portfolio_id = portfolio.portfolio_id" in backfill
    assert "RAISE EXCEPTION" in backfill
    assert "do not assign a synthetic or deployment-default tenant" in backfill
    assert operations[2][0:3] == (
        "alter_column",
        "analytics_export_jobs",
        "tenant_id",
    )
    assert operations[2][3]["nullable"] is False
    assert (
        "create_fk",
        "fk_analytics_export_jobs_tenant_portfolio",
        "analytics_export_jobs",
        "portfolios",
        ("tenant_id", "portfolio_id"),
        ("tenant_id", "portfolio_id"),
    ) in operations
    assert (
        "create_index",
        "ix_analytics_export_jobs_tenant_dataset_fingerprint_id",
        "analytics_export_jobs",
        ("tenant_id", "dataset_type", "request_fingerprint", "id DESC"),
        {},
    ) in operations
    assert operations[-3:] == [
        (
            "drop_constraint",
            "fk_analytics_export_jobs_tenant_portfolio",
            "analytics_export_jobs",
            {"type_": "foreignkey"},
        ),
        (
            "drop_constraint",
            "ck_analytics_export_jobs_tenant_authority",
            "analytics_export_jobs",
            {"type_": "check"},
        ),
        ("drop_column", "analytics_export_jobs", "tenant_id"),
    ]
