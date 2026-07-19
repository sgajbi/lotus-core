"""Executable contract proof for aggregation revision lineage persistence."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c117b2c3d4f6_feat_add_aggregation_revision_lineage.py"
)


def test_aggregation_revision_lineage_migration_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(("add_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, condition)
        ),
    )
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns: operations.append(
            ("create_index", name, table, tuple(columns))
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

    migration = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c117b2c3d4f6"
    assert migration["down_revision"] == "c116b2c3d4f5"
    assert [operation[0] for operation in operations] == [
        "add_column",
        "create_check_constraint",
        "add_column",
        "create_check_constraint",
        "create_index",
        "drop_index",
        "drop_constraint",
        "drop_column",
        "drop_constraint",
        "drop_column",
    ]
    assert operations[0][1] == "pipeline_stage_state"
    assert operations[0][2].name == "aggregation_revision"
    assert operations[0][2].nullable is False
    assert operations[2][1] == "financial_reconciliation_runs"
    assert operations[2][2].name == "aggregation_revision"
    assert operations[2][2].nullable is True
    assert operations[4][1:3] == (
        "ix_fin_recon_scope_revision_type",
        "financial_reconciliation_runs",
    )
