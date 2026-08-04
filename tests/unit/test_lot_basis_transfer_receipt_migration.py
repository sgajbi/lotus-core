"""Executable migration contract for immutable lot basis-transfer receipts."""

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
    / "c146b2c3d513_feat_add_lot_basis_transfer_receipts.py"
)


def test_lot_basis_transfer_receipt_migration_is_reversible(monkeypatch) -> None:
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
    monkeypatch.setattr(op, "drop_table", lambda name: operations.append(("drop_table", name)))
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c146b2c3d513"
    assert migration["down_revision"] == "c145b2c3d512"
    created_tables = [operation[1] for operation in operations if operation[0] == "create_table"]
    assert created_tables == [
        "lot_basis_transfer_receipts",
        "lot_basis_transfer_allocations",
    ]
    assert operations.index(("drop_table", "lot_basis_transfer_allocations")) < operations.index(
        ("drop_table", "lot_basis_transfer_receipts")
    )

    receipt_definitions = next(
        operation[2]
        for operation in operations
        if operation[:2] == ("create_table", "lot_basis_transfer_receipts")
    )
    receipt_columns = {
        definition.name: definition
        for definition in receipt_definitions
        if isinstance(definition, Column)
    }
    assert isinstance(receipt_columns["transaction_calculation_lineage"].type, JSONB)
    assert isinstance(receipt_columns["basis_transfer_calculation_lineage"].type, JSONB)
    receipt_constraints = {
        definition.name
        for definition in receipt_definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_lot_basis_transfer_receipt_lifecycle",
        "ck_lot_basis_transfer_receipt_chain",
        "ck_lot_basis_transfer_receipt_hashes",
        "fk_lot_basis_transfer_receipt_source_tx",
        "fk_lot_basis_transfer_receipt_source_security",
        "uq_lot_basis_transfer_receipt_version",
        "uq_lot_basis_transfer_receipt_scope_version",
        "uq_lot_basis_transfer_source_tx_version",
    } <= receipt_constraints
    assert not any(
        name and "target" in name and name.startswith("fk_") for name in receipt_constraints
    )

    allocation_definitions = next(
        operation[2]
        for operation in operations
        if operation[:2] == ("create_table", "lot_basis_transfer_allocations")
    )
    allocation_constraints = {
        definition.name
        for definition in allocation_definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_lot_basis_transfer_allocation_conservation",
        "fk_lot_basis_transfer_allocation_receipt",
        "fk_lot_basis_transfer_allocation_source_tx",
        "fk_lot_basis_transfer_allocation_lot_scope",
        "uq_lot_basis_transfer_allocation_ordinal",
        "uq_lot_basis_transfer_allocation_source_lot",
    } <= allocation_constraints
