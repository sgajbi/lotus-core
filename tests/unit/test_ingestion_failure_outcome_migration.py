"""Executable contract proof for the ingestion failure-outcome migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c121b2c3d4fa_feat_add_ingestion_failure_outcomes.py"
)


def test_ingestion_failure_outcome_migration_is_bounded_and_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(
            ("add_column", table, column.name, str(column.type), column.nullable)
        ),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition, **kwargs: operations.append(
            ("create_check", table, name, condition, kwargs)
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
        lambda name, table, **kwargs: operations.append(("drop_check", table, name, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c121b2c3d4fa"
    assert migration["down_revision"] == "c120b2c3d4f9"
    assert operations[:4] == [
        ("add_column", "ingestion_jobs", "failure_status_code", "INTEGER", True),
        ("add_column", "ingestion_jobs", "failure_code", "VARCHAR", True),
        ("add_column", "ingestion_jobs", "failure_detail", "JSON", True),
        ("add_column", "ingestion_jobs", "failure_headers", "JSON", True),
    ]
    assert operations[4][0:3] == (
        "create_check",
        "ingestion_jobs",
        "ck_ingestion_jobs_failure_outcome_complete",
    )
    assert operations[4][4] == {"postgresql_not_valid": True}
    assert "failure_status_code IS NOT NULL" in operations[4][3]
    assert operations[5] == (
        "execute",
        'ALTER TABLE "ingestion_jobs" '
        'VALIDATE CONSTRAINT "ck_ingestion_jobs_failure_outcome_complete"',
    )
    assert operations[6:] == [
        (
            "drop_check",
            "ingestion_jobs",
            "ck_ingestion_jobs_failure_outcome_complete",
            {"type_": "check"},
        ),
        ("drop_column", "ingestion_jobs", "failure_headers"),
        ("drop_column", "ingestion_jobs", "failure_detail"),
        ("drop_column", "ingestion_jobs", "failure_code"),
        ("drop_column", "ingestion_jobs", "failure_status_code"),
    ]
