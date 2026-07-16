"""Executable contract tests for the aggregation-job lease migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import MagicMock

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c111b2c3d4f0_feat_add_aggregation_job_leases.py"
)


def test_aggregation_job_lease_migration_is_reversible(monkeypatch) -> None:
    add_column = MagicMock()
    create_check_constraint = MagicMock()
    create_index = MagicMock()
    drop_index = MagicMock()
    drop_constraint = MagicMock()
    drop_column = MagicMock()
    monkeypatch.setattr(op, "add_column", add_column)
    monkeypatch.setattr(op, "create_check_constraint", create_check_constraint)
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    monkeypatch.setattr(op, "drop_constraint", drop_constraint)
    monkeypatch.setattr(op, "drop_column", drop_column)
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert [call.args[1].name for call in add_column.call_args_list] == [
        "lease_owner",
        "lease_token",
        "lease_expires_at",
    ]
    create_check_constraint.assert_called_once()
    create_index.assert_called_once_with(
        "ix_portfolio_aggregation_jobs_status_lease_expiry",
        "portfolio_aggregation_jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )
    drop_index.assert_called_once_with(
        "ix_portfolio_aggregation_jobs_status_lease_expiry",
        table_name="portfolio_aggregation_jobs",
    )
    drop_constraint.assert_called_once_with(
        "ck_portfolio_aggregation_jobs_lease_complete",
        "portfolio_aggregation_jobs",
        type_="check",
    )
    assert [call.args[1] for call in drop_column.call_args_list] == [
        "lease_expires_at",
        "lease_token",
        "lease_owner",
    ]
