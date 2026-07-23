"""Executable contract proof for staged portfolio valuation authority."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c118b2c3d4f7_feat_add_portfolio_valuation_book_scope.py"
)


def test_portfolio_valuation_book_scope_migration_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(("add_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, condition)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c118b2c3d4f7"
    assert migration["down_revision"] == "c117b2c3d4f6"
    assert [operation[0] for operation in operations] == [
        "add_column",
        "add_column",
        "create_check_constraint",
        "drop_constraint",
        "drop_column",
        "drop_column",
    ]
    assert operations[0][1] == "portfolios"
    assert operations[0][2].name == "tenant_id"
    assert operations[0][2].nullable is True
    assert operations[1][2].name == "legal_book_id"
    assert operations[1][2].nullable is True
    assert operations[2][1] == "ck_portfolios_valuation_book_scope_complete"
    assert "tenant_id = btrim(tenant_id)" in operations[2][3]
    assert "legal_book_id = btrim(legal_book_id)" in operations[2][3]
    assert "tenant_id <> ''" in operations[2][3]
    assert "legal_book_id <> ''" in operations[2][3]
    assert operations[-2:] == [
        ("drop_column", "portfolios", "legal_book_id"),
        ("drop_column", "portfolios", "tenant_id"),
    ]
