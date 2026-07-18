"""Executable contract proof for portfolio party-role persistence."""

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
    / "c115b2c3d4f4_feat_add_portfolio_party_role_assignments.py"
)


def test_portfolio_party_role_migration_is_constrained_indexed_and_reversible(
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

    assert migration["revision"] == "c115b2c3d4f4"
    assert migration["down_revision"] == "c114b2c3d4f3"
    assert [operation[0] for operation in operations] == [
        "create_table",
        "create_index",
        "create_index",
        "create_index",
        "drop_index",
        "drop_index",
        "drop_index",
        "drop_table",
    ]

    _, table_name, definitions = operations[0]
    assert table_name == "portfolio_party_role_assignments"
    columns = {
        definition.name: definition for definition in definitions if isinstance(definition, Column)
    }
    assert columns["source_system"].nullable is False
    assert columns["source_record_id"].nullable is False
    assert columns["observed_at"].nullable is False

    constraints = {
        definition.name: definition
        for definition in definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_party_role_effective_window",
        "ck_party_role_assignment_version_positive",
        "ck_party_role_type_governed",
        "ck_party_role_scope_governed",
        "ck_party_role_quality_governed",
        "uq_party_role_source_record_version",
    } <= constraints.keys()
    assert any(isinstance(value, ForeignKeyConstraint) for value in constraints.values())
    assert operations[-1] == ("drop_table", "portfolio_party_role_assignments")
