"""Regression proof for the ordered outbox stream lookup migration."""

from __future__ import annotations

import runpy
from pathlib import Path

from sqlalchemy.sql.elements import TextClause

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c129b2c3d502_perf_add_outbox_stream_order_index.py"
)


def test_outbox_stream_order_migration_is_partial_and_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns, **kwargs: operations.append(
            ("create_index", name, table, columns, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
    )

    migration = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert len(operations) == 2
    _, name, table, columns, kwargs = operations[0]
    assert name == "ix_outbox_events_stream_unresolved_order"
    assert table == "outbox_events"
    assert columns == ["topic", "partition_key", "created_at", "id"]
    assert kwargs["unique"] is False
    predicate = kwargs["postgresql_where"]
    assert isinstance(predicate, TextClause)
    assert str(predicate) == "status IN ('PENDING', 'FAILED')"
    assert operations[1] == (
        "drop_index",
        "ix_outbox_events_stream_unresolved_order",
        {"table_name": "outbox_events"},
    )
