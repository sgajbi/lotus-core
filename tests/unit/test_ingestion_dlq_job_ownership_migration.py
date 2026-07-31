"""Executable contract proof for durable ingestion DLQ ownership."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c133b2c3d506_feat_add_ingestion_dlq_job_ownership.py"
)


def test_ingestion_dlq_job_ownership_migration_is_bounded_and_reversible(
    monkeypatch,
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
        "create_foreign_key",
        lambda name, source, target, local, remote, **kwargs: operations.append(
            ("create_fk", name, source, target, local, remote, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns, **kwargs: operations.append(
            ("create_index", name, table, tuple(map(str, columns)), kwargs)
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
        lambda name, table, **kwargs: operations.append(
            ("drop_constraint", name, table, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c133b2c3d506"
    assert migration["down_revision"] == "c132b2c3d505"
    assert operations[:2] == [
        ("add_column", "consumer_dlq_events", "ingestion_job_id", True),
        ("add_column", "outbox_events", "ingestion_job_id", True),
    ]
    backfill = operations[2][1]
    assert "GROUP BY dlq.id" in backfill
    assert "HAVING count(*) = 1" in backfill
    assert operations[3][-1] == {"postgresql_not_valid": True}
    assert "VALIDATE CONSTRAINT" in operations[4][1]
    assert operations[5][0:3] == (
        "create_index",
        "ix_consumer_dlq_events_job_observed_id",
        "consumer_dlq_events",
    )
    assert operations[6][0:3] == (
        "create_index",
        "ix_consumer_dlq_replay_audit_job_requested_id",
        "consumer_dlq_replay_audit",
    )
    assert operations[-5:] == [
        (
            "drop_index",
            "ix_consumer_dlq_replay_audit_job_requested_id",
            {"table_name": "consumer_dlq_replay_audit"},
        ),
        (
            "drop_index",
            "ix_consumer_dlq_events_job_observed_id",
            {"table_name": "consumer_dlq_events"},
        ),
        (
            "drop_constraint",
            "fk_consumer_dlq_events_ingestion_job_id",
            "consumer_dlq_events",
            {"type_": "foreignkey"},
        ),
        ("drop_column", "outbox_events", "ingestion_job_id"),
        ("drop_column", "consumer_dlq_events", "ingestion_job_id"),
    ]
