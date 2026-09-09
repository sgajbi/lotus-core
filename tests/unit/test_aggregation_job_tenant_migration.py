"""Guard the aggregation-job tenant migration contract without PostgreSQL."""

import runpy
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c168b2c3d52f_feat_add_aggregation_job_tenant.py"
)


def test_aggregation_job_tenant_migration_is_fail_closed_and_reversible() -> None:
    migration = runpy.run_path(str(MIGRATION))
    constants = migration["upgrade"].__code__.co_consts
    upgrade_text = "\n".join(value for value in constants if isinstance(value, str))

    assert migration["down_revision"] == "c167b2c3d52e"
    assert "LOCK TABLE portfolio_aggregation_jobs IN ACCESS EXCLUSIVE MODE" in upgrade_text
    assert "SET LOCAL lock_timeout = '5s'" in upgrade_text
    assert "SET tenant_id = portfolio.tenant_id" in upgrade_text
    assert "unattributable row(s)" in upgrade_text
    assert "never assign a synthetic tenant" in upgrade_text
    assert callable(migration["downgrade"])
