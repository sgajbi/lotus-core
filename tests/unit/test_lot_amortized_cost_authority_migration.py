"""Executable contract proof for lot amortized-cost source authority."""

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
    / "c140b2c3d50d_feat_add_lot_amortized_cost_authority.py"
)


def test_lot_amortized_cost_authority_migration_is_reversible(monkeypatch) -> None:
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
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "alter_column",
        lambda table, column, **kwargs: operations.append(("alter_column", table, column, kwargs)),
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

    assert migration["revision"] == "c140b2c3d50d"
    assert migration["down_revision"] == "c139b2c3d50c"
    assert [operation[0] for operation in operations].count("alter_column") == 4
    assert [operation[0] for operation in operations].count("drop_constraint") == 4
    assert [operation[0] for operation in operations].count("create_check_constraint") == 4
    create_table = next(
        operation
        for operation in operations
        if operation[:2] == ("create_table", "lot_amortized_cost_authority")
    )
    definitions = create_table[2]
    columns = {
        definition.name: definition for definition in definitions if isinstance(definition, Column)
    }
    assert set(columns) == {
        "id",
        "authority_type",
        "tenant_id",
        "legal_book_id",
        "portfolio_id",
        "security_id",
        "lot_id",
        "valid_from",
        "valid_to",
        "lifecycle_status",
        "source_version",
        "source_system",
        "source_record_id",
        "source_revision",
        "observed_at",
        "authority_content_hash",
        "authority_payload",
        "created_at",
    }
    assert isinstance(columns["authority_payload"].type, JSONB)
    constraints = {
        definition.name: definition
        for definition in definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_lot_amort_authority_type",
        "ck_lot_amort_authority_scope_normalized",
        "ck_lot_amort_authority_effective_window",
        "ck_lot_amort_authority_status",
        "ck_lot_amort_authority_version_positive",
        "ck_lot_amort_authority_source_normalized",
        "ck_lot_amort_authority_hash",
        "ck_lot_amort_authority_payload_object",
        "fk_lot_amort_authority_book_scope",
        "fk_lot_amort_authority_security",
        "fk_lot_amort_authority_lot_scope",
        "uq_lot_amort_authority_source_version",
    } <= constraints.keys()
    assert ("drop_table", "lot_amortized_cost_authority") in operations
