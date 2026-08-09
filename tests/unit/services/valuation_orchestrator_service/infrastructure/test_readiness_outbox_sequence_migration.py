"""Executable contract proof for the readiness outbox sequence migration."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c150b2c3d517_feat_add_readiness_outbox_sequence.py"
)


def test_readiness_outbox_sequence_is_defaulted_reversible_and_linear(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
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

    migration = runpy.run_path(str(MIGRATION))
    assert migration["revision"] == "c150b2c3d517"
    assert migration["down_revision"] == "c149b2c3d516"

    migration["upgrade"]()
    operation, table_name, column = operations.pop(0)
    assert operation == "add_column"
    assert table_name == "portfolio_valuation_jobs"
    assert column.name == "claimed_readiness_outbox_id"
    assert column.nullable is False
    assert str(column.server_default.arg) == "0"

    migration["downgrade"]()
    assert operations == [
        ("drop_column", "portfolio_valuation_jobs", "claimed_readiness_outbox_id")
    ]
