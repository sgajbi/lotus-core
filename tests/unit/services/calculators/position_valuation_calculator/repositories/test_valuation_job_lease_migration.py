"""Executable contract tests for the valuation-job lease migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import MagicMock

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[6]
    / "alembic"
    / "versions"
    / "c156b2c3d523_feat_add_valuation_claim_leases.py"
)


def test_valuation_job_lease_migration_is_reversible_and_requeues_legacy_claims(
    monkeypatch,
) -> None:
    add_column = MagicMock()
    execute = MagicMock()
    create_check_constraint = MagicMock()
    create_index = MagicMock()
    drop_index = MagicMock()
    drop_constraint = MagicMock()
    drop_column = MagicMock()
    monkeypatch.setattr(op, "add_column", add_column)
    monkeypatch.setattr(op, "execute", execute)
    monkeypatch.setattr(op, "create_check_constraint", create_check_constraint)
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    monkeypatch.setattr(op, "drop_constraint", drop_constraint)
    monkeypatch.setattr(op, "drop_column", drop_column)
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert [call.args[1].name for call in add_column.call_args_list] == [
        "valuation_lease_owner",
        "valuation_lease_expires_at",
    ]
    recovery_sql = "\n".join(
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in execute.call_args_list
    )
    assert "UPDATE portfolio_valuation_jobs" in recovery_sql
    assert "status = 'PENDING'" in recovery_sql
    assert "valuation_claim_token = NULL" in recovery_sql
    assert create_check_constraint.call_count == 4
    create_index.assert_called_once()
    drop_index.assert_called_once_with(
        "ix_portfolio_valuation_jobs_processing_lease_expiry",
        table_name="portfolio_valuation_jobs",
    )
    assert drop_constraint.call_count == 4
    assert [call.args[1] for call in drop_column.call_args_list] == [
        "valuation_lease_expires_at",
        "valuation_lease_owner",
    ]
