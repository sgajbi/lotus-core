"""Executable migration contract for immutable lot-disposal receipts."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c141b2c3d50e_feat_add_lot_disposal_receipts.py"
)


def test_lot_disposal_receipt_migration_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "create_table",
        lambda name, *definitions: operations.append(("create_table", name, definitions)),
    )
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns, **kwargs: operations.append(
            ("create_index", name, table, columns, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_table",
        lambda name: operations.append(("drop_table", name)),
    )
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c141b2c3d50e"
    assert migration["down_revision"] == "c140b2c3d50d"
    created_tables = [operation[1] for operation in operations if operation[0] == "create_table"]
    assert created_tables == ["lot_disposal_receipts", "lot_disposal_allocations"]
    assert ("drop_table", "lot_disposal_allocations") in operations
    assert ("drop_table", "lot_disposal_receipts") in operations
    assert operations.index(("drop_table", "lot_disposal_allocations")) < operations.index(
        ("drop_table", "lot_disposal_receipts")
    )

    receipt_definitions = next(
        operation[2]
        for operation in operations
        if operation[:2] == ("create_table", "lot_disposal_receipts")
    )
    receipt_columns = {
        definition.name: definition
        for definition in receipt_definitions
        if isinstance(definition, Column)
    }
    assert isinstance(receipt_columns["transaction_calculation_lineage"].type, JSONB)
    assert isinstance(receipt_columns["disposal_calculation_lineage"].type, JSONB)
    receipt_constraints = {
        definition.name
        for definition in receipt_definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_lot_disposal_receipt_lifecycle",
        "ck_lot_disposal_receipt_chain",
        "ck_lot_disposal_receipt_hashes",
        "fk_lot_disposal_receipt_transaction",
        "fk_lot_disposal_receipt_security",
        "uq_lot_disposal_receipt_version",
        "uq_lot_disposal_receipt_scope_version",
        "uq_lot_disposal_transaction_version",
    } <= receipt_constraints

    allocation_definitions = next(
        operation[2]
        for operation in operations
        if operation[:2] == ("create_table", "lot_disposal_allocations")
    )
    allocation_constraints = {
        definition.name
        for definition in allocation_definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "fk_lot_disposal_allocation_receipt",
        "fk_lot_disposal_allocation_source_tx",
        "fk_lot_disposal_allocation_lot_scope",
        "uq_lot_disposal_allocation_ordinal",
        "uq_lot_disposal_allocation_source_lot",
    } <= allocation_constraints
