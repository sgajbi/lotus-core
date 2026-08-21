"""Contract tests for the legacy position-state authority backfill."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c159b2c3d526_fix_backfill_legacy_position_state.py"
)


def test_position_state_backfill_is_conservative_idempotent_and_irreversible(monkeypatch) -> None:
    executed: list[object] = []
    monkeypatch.setattr(op, "execute", executed.append)
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c159b2c3d526"
    assert migration["down_revision"] == "c158b2c3d525"
    assert len(executed) == 1
    sql = " ".join(str(executed[0]).split()).upper()
    assert "FROM POSITION_HISTORY" in sql
    assert "FROM DAILY_POSITION_SNAPSHOTS" in sql
    assert "MAX(EPOCH) AS EPOCH" in sql
    assert "FILTER (WHERE EVIDENCE.EVIDENCE_KIND = 'HISTORY') - 1" in sql
    assert "FILTER (WHERE EVIDENCE.EVIDENCE_KIND = 'SNAPSHOT')" in sql
    assert "WHEN BOOL_OR(EVIDENCE.EVIDENCE_KIND = 'HISTORY') THEN 'REPROCESSING'" in sql
    assert "ELSE 'SNAPSHOT_ONLY'" in sql
    assert "NOT EXISTS" in sql
    assert "BTRIM(EXISTING.SECURITY_ID) = EVIDENCE.SECURITY_ID" in sql
    assert "ON CONFLICT (PORTFOLIO_ID, SECURITY_ID) DO NOTHING" in sql
    assert "UPDATE POSITION_STATE" not in sql
    assert "DELETE FROM POSITION_STATE" not in sql
