"""Regression proof for the durable outbox partition-key migration."""

from __future__ import annotations

import runpy
from pathlib import Path

from sqlalchemy import Column, String

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c113b2c3d4f2_feat_add_outbox_partition_key.py"
)


def test_outbox_partition_key_migration_backfills_before_enforcement_and_downgrades(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(("add_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "execute",
        lambda statement: operations.append(("execute", statement)),
    )
    monkeypatch.setattr(
        op,
        "alter_column",
        lambda table, column, **kwargs: operations.append(("alter_column", table, column, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert [operation[0] for operation in operations] == [
        "add_column",
        "execute",
        "alter_column",
        "drop_column",
    ]
    _, table, column = operations[0]
    assert table == "outbox_events"
    assert isinstance(column, Column)
    assert column.name == "partition_key"
    assert isinstance(column.type, String)
    assert column.nullable is True
    normalized_backfill = " ".join(str(operations[1][1]).split()).upper()
    assert normalized_backfill == (
        "UPDATE OUTBOX_EVENTS SET PARTITION_KEY = AGGREGATE_ID WHERE PARTITION_KEY IS NULL"
    )
    assert operations[2] == (
        "alter_column",
        "outbox_events",
        "partition_key",
        {"nullable": False},
    )
    assert operations[3] == ("drop_column", "outbox_events", "partition_key")
