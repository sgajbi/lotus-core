"""Guard the reconciliation tenant migration contract without PostgreSQL."""

import runpy
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c174b2c3d535_scope_financial_reconciliation_tenant.py"
)


def test_reconciliation_tenant_migration_is_fail_closed_and_reversible() -> None:
    migration = runpy.run_path(str(MIGRATION))
    source = MIGRATION.read_text(encoding="utf-8")

    assert migration["down_revision"] == "c173b2c3d534"
    assert "IN ACCESS EXCLUSIVE MODE" in source
    assert "SET LOCAL lock_timeout = '5s'" in source
    assert "SET authority_scope = 'TENANT', tenant_id = portfolio.tenant_id" in source
    assert "SET authority_scope = 'ESTATE', tenant_id = NULL" in source
    assert "financial-reconciliation-requested" in source
    assert "event-fence tenant cutover" in source
    assert "never invent a tenant" in source
    assert "global dedupe collision(s)" in source
    assert callable(migration["downgrade"])
