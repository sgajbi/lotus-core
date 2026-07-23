"""Executable contract proof for exact-scope market-price authority persistence."""

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
    / "c119b2c3d4f8_feat_add_market_price_source_facts.py"
)


def test_market_price_source_fact_migration_is_reversible(monkeypatch) -> None:
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

    assert migration["revision"] == "c119b2c3d4f8"
    assert migration["down_revision"] == "c118b2c3d4f7"
    assert [operation[0] for operation in operations] == [
        "create_table",
        "create_index",
        "drop_index",
        "drop_table",
    ]

    _, table_name, definitions = operations[0]
    assert table_name == "market_price_source_facts"
    columns = {
        definition.name: definition for definition in definitions if isinstance(definition, Column)
    }
    assert set(columns) == {
        "id",
        "tenant_id",
        "legal_book_id",
        "security_id",
        "price_date",
        "price",
        "currency",
        "quote_basis",
        "fact_status",
        "fact_version",
        "source_system",
        "source_record_id",
        "source_revision",
        "source_content_hash",
        "observed_at",
        "created_at",
    }
    assert all(column.nullable is False for column in columns.values())
    assert columns["price"].type.precision is None
    assert columns["price"].type.scale is None

    constraints = {
        definition.name: definition
        for definition in definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_market_price_source_fact_scope_normalized",
        "ck_market_price_source_fact_price_positive",
        "ck_market_price_source_fact_price_finite",
        "ck_market_price_source_fact_currency_normalized",
        "ck_market_price_source_fact_quote_basis",
        "ck_market_price_source_fact_status",
        "ck_market_price_source_fact_version_positive",
        "ck_market_price_source_fact_source_normalized",
        "ck_market_price_source_fact_source_hash",
        "ck_market_price_source_fact_observed_at_finite",
        "uq_market_price_source_fact_version",
    } <= constraints.keys()
    assert (
        str(constraints["ck_market_price_source_fact_price_finite"].sqltext)
        == "price <> 'NaN'::numeric AND price <> 'Infinity'::numeric"
    )
    assert (
        str(constraints["ck_market_price_source_fact_observed_at_finite"].sqltext)
        == "isfinite(observed_at)"
    )
    assert any(isinstance(value, ForeignKeyConstraint) for value in constraints.values())
    assert operations[1] == (
        "create_index",
        "ix_market_price_fact_scope_history",
        "market_price_source_facts",
        [
            "tenant_id",
            "legal_book_id",
            "security_id",
            "price_date",
            "source_system",
            "source_record_id",
        ],
    )
    assert operations[-1] == ("drop_table", "market_price_source_facts")
