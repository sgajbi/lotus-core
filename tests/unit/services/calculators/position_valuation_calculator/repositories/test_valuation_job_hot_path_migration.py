"""Executable contract for the valuation-job hot-path index migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import MagicMock

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[6]
    / "alembic"
    / "versions"
    / "c160b2c3d527_perf_bound_valuation_job_hot_paths.py"
)


def test_valuation_job_hot_path_index_migration_is_reversible(monkeypatch) -> None:
    create_index = MagicMock()
    drop_index = MagicMock()
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert [call.args[:3] for call in create_index.call_args_list] == [
        (
            "ix_portfolio_valuation_jobs_processing_lease_recovery",
            "portfolio_valuation_jobs",
            ["valuation_lease_expires_at", "id"],
        ),
        (
            "ix_portfolio_valuation_jobs_processing_lease_expiry",
            "portfolio_valuation_jobs",
            ["valuation_lease_expires_at"],
        ),
    ]
    assert all(
        str(call.kwargs["postgresql_where"]) == "status = 'PROCESSING'"
        for call in create_index.call_args_list
    )
    assert [call.args for call in drop_index.call_args_list] == [
        ("ix_portfolio_valuation_jobs_processing_lease_expiry",),
        ("ix_portfolio_valuation_jobs_processing_lease_recovery",),
    ]
    assert all(
        call.kwargs == {"table_name": "portfolio_valuation_jobs"}
        for call in drop_index.call_args_list
    )
