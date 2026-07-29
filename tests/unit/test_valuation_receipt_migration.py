"""Executable contract proof for durable valuation receipt persistence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, UniqueConstraint

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c128b2c3d501_feat_add_valuation_receipts.py"
)


def test_valuation_receipt_migration_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []

    def record_create_table(name: str, *definitions: Any) -> None:
        operations.append(("create_table", name, definitions))

    monkeypatch.setattr(op, "create_table", record_create_table)
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns: operations.append(("create_index", name, table, columns)),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
    )
    monkeypatch.setattr(op, "drop_table", lambda name: operations.append(("drop_table", name)))
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c128b2c3d501"
    assert migration["down_revision"] == "c127b2c3d500"
    assert [operation[0] for operation in operations] == [
        "create_table",
        "create_index",
        "drop_index",
        "drop_table",
    ]
    _, table_name, definitions = operations[0]
    assert table_name == "daily_position_valuation_receipts"
    columns = {
        definition.name: definition for definition in definitions if isinstance(definition, Column)
    }
    assert set(columns) == {
        "id",
        "snapshot_id",
        "supportability",
        "supportability_reasons",
        "policy_id",
        "policy_version",
        "assignment_version",
        "assignment_content_hash",
        "policy_assignment_source",
        "quote_basis",
        "price_fact_version",
        "price_fact_content_hash",
        "market_price_source",
        "calculation_lineage",
        "receipt_hash",
        "created_at",
        "updated_at",
    }
    assert columns["supportability"].nullable is False
    assert columns["supportability_reasons"].nullable is False
    assert columns["receipt_hash"].nullable is False
    constraints = {
        definition.name: definition
        for definition in definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_daily_position_valuation_receipt_supportability",
        "ck_daily_position_valuation_receipt_reasons_nonempty",
        "ck_daily_position_valuation_receipt_evidence_complete",
        "ck_daily_position_valuation_receipt_assignment_hash",
        "ck_daily_position_valuation_receipt_price_hash",
        "ck_daily_position_valuation_receipt_hash",
        "uq_daily_position_valuation_receipt_snapshot",
    } <= constraints.keys()
    foreign_key = next(
        value for value in constraints.values() if isinstance(value, ForeignKeyConstraint)
    )
    assert foreign_key.ondelete == "CASCADE"
    assert operations[-1] == ("drop_table", "daily_position_valuation_receipts")
