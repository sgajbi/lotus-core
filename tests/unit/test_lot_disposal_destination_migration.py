"""Executable migration contract for discriminated disposal destinations."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import Column

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c147b2c3d514_feat_add_lot_disposal_destinations.py"
)


def test_disposal_destination_migration_is_additive_constrained_and_reversible(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(("add_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, str(condition))
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
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

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c147b2c3d514"
    assert migration["down_revision"] == "c146b2c3d513"
    added = [operation for operation in operations if operation[0] == "add_column"]
    assert [operation[2].name for operation in added] == [
        "destination_type",
        "target_transaction_id",
        "target_lot_id",
        "target_instrument_id",
        "external_destination_reference",
    ]
    assert all(isinstance(operation[2], Column) and operation[2].nullable for operation in added)
    destination_check = next(
        operation[3]
        for operation in operations
        if operation[:2]
        == (
            "create_check_constraint",
            "ck_lot_disposal_receipt_destination",
        )
    )
    assert "destination_type = 'INTERNAL_LOT'" in destination_check
    assert "target_lot_id = 'LOT-' || target_transaction_id" in destination_check
    assert "destination_type = 'EXTERNAL_TRANSFER'" in destination_check
    assert "target_transaction_id IS NULL" in destination_check
    assert [operation[2] for operation in operations if operation[0] == "drop_column"] == [
        "external_destination_reference",
        "target_instrument_id",
        "target_lot_id",
        "target_transaction_id",
        "destination_type",
    ]
