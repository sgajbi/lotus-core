"""Executable contract proof for reconciliation finding lifecycle evidence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c132b2c3d505_feat_add_reconciliation_finding_evidence.py"
)


def test_reconciliation_finding_evidence_migration_is_additive_and_reversible(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    for name in (
        "add_column",
        "alter_column",
        "create_check_constraint",
        "create_index",
        "drop_index",
        "drop_constraint",
        "drop_column",
        "execute",
    ):
        monkeypatch.setattr(
            op,
            name,
            lambda *args, _name=name, **kwargs: operations.append((_name, *args, kwargs)),
        )
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c132b2c3d505"
    assert migration["down_revision"] == "c131b2c3d504"
    assert [operation[2].name for operation in operations if operation[0] == "add_column"] == [
        "owner",
        "resolution_state",
        "resolution_actor",
        "resolved_at",
        "tolerance",
        "observed_delta",
        "repair_recommendation",
    ]
    execute_sql = "\n".join(
        str(operation[1]) for operation in operations if operation[0] == "execute"
    )
    assert "UPDATE financial_reconciliation_findings" in execute_sql
    assert "VALUATION_OPERATIONS" in execute_sql
    assert "REGENERATE_CASHFLOW" in execute_sql
    assert "VALIDATE CONSTRAINT" in execute_sql
    assert (
        len([operation for operation in operations if operation[0] == "create_check_constraint"])
        == 7
    )
    assert len([operation for operation in operations if operation[0] == "drop_column"]) == 7
