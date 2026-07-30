"""Executable contract for optional legacy valuation calculation lineage."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c131b2c3d504_feat_allow_legacy_valuation_lineage.py"
)


def test_legacy_valuation_lineage_constraint_migration_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, condition)
        ),
    )
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c131b2c3d504"
    assert migration["down_revision"] == "c130b2c3d503"
    assert [operation[0] for operation in operations] == [
        "drop_constraint",
        "create_check_constraint",
        "drop_constraint",
        "create_check_constraint",
    ]
    upgrade_condition = str(operations[1][3])
    downgrade_condition = str(operations[3][3])
    assert "market_price_source IS NULL" in upgrade_condition
    assert "market_price_source IS NULL AND calculation_lineage IS NULL" not in upgrade_condition
    assert "market_price_source IS NULL AND calculation_lineage IS NULL" in downgrade_condition
