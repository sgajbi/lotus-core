"""Executable contract proof for instrument valuation-policy assignment persistence."""

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
    / "c116b2c3d4f5_feat_add_instrument_valuation_policy_assignments.py"
)


def test_instrument_valuation_policy_assignment_migration_is_reversible(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []

    def record_create_table(name: str, *definitions: Any) -> None:
        operations.append(("create_table", name, definitions))

    monkeypatch.setattr(op, "create_table", record_create_table)
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
    migration = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c116b2c3d4f5"
    assert migration["down_revision"] == "c115b2c3d4f4"
    assert [operation[0] for operation in operations] == [
        "create_table",
        "create_index",
        "create_index",
        "drop_index",
        "drop_index",
        "drop_table",
    ]

    _, table_name, definitions = operations[0]
    assert table_name == "instrument_valuation_policy_assignments"
    columns = {
        definition.name: definition for definition in definitions if isinstance(definition, Column)
    }
    for field_name in (
        "tenant_id",
        "legal_book_id",
        "security_id",
        "policy_id",
        "source_system",
        "source_record_id",
        "source_revision",
        "observed_at",
    ):
        assert columns[field_name].nullable is False

    constraints = {
        definition.name: definition
        for definition in definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_inst_val_policy_effective_window",
        "ck_inst_val_policy_version_positive",
        "ck_inst_val_assignment_version_positive",
        "ck_inst_val_assignment_status_governed",
        "uq_inst_val_policy_source_version",
    } <= constraints.keys()
    assert any(isinstance(value, ForeignKeyConstraint) for value in constraints.values())
    assert operations[-1] == ("drop_table", "instrument_valuation_policy_assignments")
