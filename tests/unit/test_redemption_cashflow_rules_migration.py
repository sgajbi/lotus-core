"""Execute the reversible redemption cashflow-rule migration contract."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy.sql.elements import TextClause

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c149b2c3d516_feat_add_redemption_cashflow_rules.py"
)


def test_redemption_cashflow_rules_are_canonical_idempotent_and_reversible(monkeypatch) -> None:
    statements: list[TextClause] = []
    monkeypatch.setattr(op, "execute", statements.append)

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c149b2c3d516"
    assert migration["down_revision"] == "c148b2c3d515"
    assert len(statements) == 2
    upgrade_sql, downgrade_sql = (str(statement) for statement in statements)
    for transaction_type in (
        "MATURITY_REDEMPTION",
        "CALL_REDEMPTION",
        "PARTIAL_REDEMPTION",
    ):
        assert transaction_type in upgrade_sql
        assert transaction_type in downgrade_sql
    assert "INVESTMENT_INFLOW" in upgrade_sql
    assert "ON CONFLICT (transaction_type) DO UPDATE" in upgrade_sql
    assert "is_position_flow = EXCLUDED.is_position_flow" in upgrade_sql
    assert "DELETE FROM cashflow_rules" in downgrade_sql
