"""Executable contract tests for FX revaluation queue indexes."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import MagicMock

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c112b2c3d4f1_feat_add_fx_revaluation_job_indexes.py"
)


def test_fx_revaluation_job_indexes_are_partial_and_reversible(monkeypatch) -> None:
    create_index = MagicMock()
    drop_index = MagicMock()
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    unique_index, priority_index = create_index.call_args_list
    assert unique_index.args[:2] == (
        "uq_reproc_jobs_pending_fx_pair",
        "reprocessing_jobs",
    )
    assert unique_index.kwargs["unique"] is True
    assert "RESET_FX_WATERMARKS" in str(unique_index.kwargs["postgresql_where"])
    assert priority_index.args[:2] == (
        "ix_reproc_jobs_pending_fx_priority",
        "reprocessing_jobs",
    )
    assert priority_index.kwargs["unique"] is False
    assert "earliest_impacted_date" in str(priority_index.args[2][0])
    assert [call.args[0] for call in drop_index.call_args_list] == [
        "ix_reproc_jobs_pending_fx_priority",
        "uq_reproc_jobs_pending_fx_pair",
    ]
