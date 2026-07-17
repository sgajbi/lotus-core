"""Executable contract proof for the valuation requeue-fence migration."""

from __future__ import annotations

import runpy
from pathlib import Path

from sqlalchemy import Boolean, Column, String

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c114b2c3d4f3_fix_add_valuation_requeue_fence.py"
)


def test_valuation_requeue_fence_is_non_nullable_defaulted_and_reversible(
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
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c114b2c3d4f3"
    assert migration["down_revision"] == "c113b2c3d4f2"
    assert len(operations) == 4

    _, table, column = operations[0]
    assert table == "portfolio_valuation_jobs"
    assert isinstance(column, Column)
    assert column.name == "requeue_requested"
    assert isinstance(column.type, Boolean)
    assert column.nullable is False
    assert str(column.server_default.arg).lower() == "false"
    _, source_table, source_column = operations[1]
    assert source_table == "portfolio_valuation_jobs"
    assert isinstance(source_column, Column)
    assert source_column.name == "source_correction_id"
    assert isinstance(source_column.type, String)
    assert source_column.nullable is True
    assert operations[2] == (
        "drop_column",
        "portfolio_valuation_jobs",
        "source_correction_id",
    )
    assert operations[3] == (
        "drop_column",
        "portfolio_valuation_jobs",
        "requeue_requested",
    )
