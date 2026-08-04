"""Verify the additive external transfer destination migration and ORM parity."""

import runpy
from pathlib import Path
from typing import Any

from portfolio_common.database_models import Transaction
from sqlalchemy import Column, String

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c148b2c3d515_feat_add_external_transfer_destination.py"
)


def test_transaction_model_exposes_nullable_external_destination_reference() -> None:
    column = Transaction.__table__.c.external_destination_reference

    assert column.nullable is True
    assert column.type.python_type is str


def test_migration_is_linear_additive_and_reversible(monkeypatch) -> None:
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

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c148b2c3d515"
    assert migration["down_revision"] == "c147b2c3d514"
    assert len(operations) == 2
    added = operations[0]
    assert added[:2] == ("add_column", "transactions")
    assert isinstance(added[2], Column)
    assert added[2].name == "external_destination_reference"
    assert isinstance(added[2].type, String)
    assert added[2].nullable is True
    assert operations[1] == ("drop_column", "transactions", "external_destination_reference")
