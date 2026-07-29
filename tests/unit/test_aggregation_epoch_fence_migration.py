"""Executable contract proof for aggregation epoch/material revision fencing."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import MagicMock

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c127b2c3d500_feat_add_aggregation_epoch_fence.py"
)


def test_aggregation_epoch_fence_migration_is_reversible(monkeypatch) -> None:
    add_column = MagicMock()
    execute = MagicMock()
    create_check_constraint = MagicMock()
    drop_constraint = MagicMock()
    drop_column = MagicMock()
    monkeypatch.setattr(op, "add_column", add_column)
    monkeypatch.setattr(op, "execute", execute)
    monkeypatch.setattr(op, "create_check_constraint", create_check_constraint)
    monkeypatch.setattr(op, "drop_constraint", drop_constraint)
    monkeypatch.setattr(op, "drop_column", drop_column)

    migration = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c127b2c3d500"
    assert migration["down_revision"] == "c126b2c3d4ff"
    assert [call.args[1].name for call in add_column.call_args_list] == [
        "target_epoch",
        "source_revision",
    ]
    assert all(call.args[1].nullable is False for call in add_column.call_args_list)
    assert [str(call.args[1].server_default.arg) for call in add_column.call_args_list] == [
        "0",
        "1",
    ]
    backfill_sql = str(execute.call_args.args[0])
    assert "UPDATE portfolio_aggregation_jobs AS jobs" in backfill_sql
    assert "MAX(state.epoch)" in backfill_sql
    assert "BTRIM(state.portfolio_id) = BTRIM(jobs.portfolio_id)" in backfill_sql
    assert [call.args[0] for call in create_check_constraint.call_args_list] == [
        "ck_portfolio_aggregation_jobs_target_epoch_nonnegative",
        "ck_portfolio_aggregation_jobs_source_revision_positive",
    ]
    assert [call.args[0] for call in drop_constraint.call_args_list] == [
        "ck_portfolio_aggregation_jobs_source_revision_positive",
        "ck_portfolio_aggregation_jobs_target_epoch_nonnegative",
    ]
    assert [call.args[1] for call in drop_column.call_args_list] == [
        "source_revision",
        "target_epoch",
    ]
