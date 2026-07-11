"""Regression tests for cashflow-rule migration cache invalidation."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[6]
    / "alembic"
    / "versions"
    / "c104b2c3d4e9_fix_classify_ca_cash_proceeds.py"
)


def _normalized_sql(statement: object) -> str:
    return " ".join(str(statement).split()).lower()


def test_cash_consideration_rule_migration_invalidates_cache_on_upgrade_and_downgrade(
    monkeypatch,
) -> None:
    statements: list[object] = []
    monkeypatch.setattr(op, "execute", statements.append)
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert len(statements) == 2
    upgrade_sql, downgrade_sql = map(_normalized_sql, statements)
    assert "classification = 'corporate_action_proceeds'" in upgrade_sql
    assert "classification = 'income'" in downgrade_sql
    assert "updated_at = now()" in upgrade_sql
    assert "updated_at = now()" in downgrade_sql
    assert "transaction_type = 'cash_consideration'" in upgrade_sql
    assert "transaction_type = 'cash_consideration'" in downgrade_sql
