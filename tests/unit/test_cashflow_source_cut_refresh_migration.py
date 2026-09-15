"""SQL contract guard; real PostgreSQL migration/work proof is mandatory too."""

import runpy
from pathlib import Path

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c170b2c3d531_fix_streamline_cashflow_source_cut_refresh.py"
)


def test_cashflow_refresh_migration_is_linear_reversible_and_contract_preserving(monkeypatch):
    migration = runpy.run_path(str(MIGRATION))
    previous = runpy.run_path(str(MIGRATION.with_name(migration["_PREVIOUS"])))
    original = previous["_refresh_function_sql"]()
    emitted = []
    monkeypatch.setattr(op, "execute", lambda statement: emitted.append(str(statement)))
    migration["upgrade"]()
    migration["downgrade"]()
    assert migration["revision"] == "c170b2c3d531"
    assert migration["down_revision"] == "c169b2c3d530"
    assert len(emitted) == 2
    assert "LEFT JOIN cashflow_rows USING" not in emitted[0]
    assert (
        emitted[0].count("                updated_at\n                FROM selected_cashflows") == 1
    )
    assert emitted[1] == original.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    # Undo just the two work-shape changes: every economic field, ordering,
    # timestamp canonicalization, lock and materialization branch must match.
    restored = (
        emitted[0]
        .replace(
            "                id,\n"
            "                updated_at\n"
            "                FROM selected_cashflows",
            migration["_ROW_FIELDS"],
        )
        .replace("FROM cashflow_rows\n            ),", migration["_SELF_JOIN"] + "\n            ),")
    )
    assert restored == emitted[1]


@pytest.mark.parametrize("fragment", ["_CREATE", "_ROW_FIELDS", "_SELF_JOIN"])
def test_cashflow_refresh_migration_rejects_changed_historical_rewrite_premise(
    monkeypatch, fragment
):
    migration = runpy.run_path(str(MIGRATION))
    previous = runpy.run_path(str(MIGRATION.with_name(migration["_PREVIOUS"])))
    changed = previous["_refresh_function_sql"]().replace(migration[fragment], "unexpected premise")
    monkeypatch.setattr(runpy, "run_path", lambda _path: {"_refresh_function_sql": lambda: changed})
    with pytest.raises(RuntimeError, match="pinned premise"):
        migration["_refresh_sql"](linear=True)
