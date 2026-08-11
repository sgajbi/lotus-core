"""Executable contract for the corporate-action support query index."""

import runpy
from pathlib import Path
from typing import Any

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c154b2c3d521_perf_index_corporate_action_support.py"
)


def test_corporate_action_support_index_is_scoped_ordered_and_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns, **kwargs: operations.append(
            ("create_index", name, table, [str(column) for column in columns], kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c154b2c3d521"
    assert migration["down_revision"] == "c153b2c3d520"
    assert operations == [
        (
            "create_index",
            "ix_ca_event_book_scope_updated",
            "corporate_action_events",
            [
                "tenant_id",
                "legal_book_id",
                "portfolio_id",
                "updated_at DESC",
                "id DESC",
            ],
            {"unique": False},
        ),
        (
            "drop_index",
            "ix_ca_event_book_scope_updated",
            {"table_name": "corporate_action_events"},
        ),
    ]
