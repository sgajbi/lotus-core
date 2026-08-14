"""Executable contract proof for governed ingestion payload evidence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c157b2c3d524_feat_govern_ingestion_payload_evidence.py"
)


def test_ingestion_payload_evidence_migration_is_fail_closed_and_reversible(
    monkeypatch,
) -> None:
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
        lambda name, table, condition, **kwargs: operations.append(
            ("create_check", table, name, condition, kwargs)
        ),
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

    assert migration["revision"] == "c157b2c3d524"
    assert migration["down_revision"] == "c156b2c3d523"
    added_columns = [operation[2] for operation in operations if operation[0] == "add_column"]
    assert added_columns == [
        "request_payload_policy_version",
        "request_payload_classification",
        "request_payload_representation",
        "request_payload_replay_eligible",
        "request_payload_partial_replay_eligible",
        "request_payload_replay_expires_at",
        "request_payload_retention_authority",
    ]
    backfill = next(operation[1] for operation in operations if operation[0] == "execute")
    assert "request_payload = CASE" in backfill
    assert "ELSE NULL" in backfill
    assert "ingestion-evidence-policy.legacy.v0" in backfill
    assert "request_payload_replay_eligible = false" in backfill
    assert "request_payload_replay_expires_at = NULL" in backfill
    assert "lotus-core#708" in backfill
    altered_columns = [operation[2] for operation in operations if operation[0] == "alter_column"]
    assert altered_columns == [
        column for column in added_columns if not column.endswith("expires_at")
    ]
    checks = [operation for operation in operations if operation[0] == "create_check"]
    assert len(checks) == 8
    assert all(operation[4] == {"postgresql_not_valid": True} for operation in checks)
    assert (
        sum(
            operation[0] == "execute" and "VALIDATE CONSTRAINT" in operation[1]
            for operation in operations
        )
        == 8
    )
    assert [operation[2] for operation in operations if operation[0] == "drop_column"] == list(
        reversed(added_columns)
    )
