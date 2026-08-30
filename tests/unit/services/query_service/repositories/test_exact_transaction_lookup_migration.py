"""Executable contract for the exact-transaction lookup index migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c164b2c3d52b_perf_index_exact_transaction_lookup.py"
)

INDEX_NAME = "ix_transactions_portfolio_transaction_id"


def _load_migration(monkeypatch):
    ddl = MagicMock()
    migration_context = MagicMock()
    migration_context.as_sql = False
    monkeypatch.setattr(op, "create_index", ddl.create_index)
    monkeypatch.setattr(op, "drop_index", ddl.drop_index)
    monkeypatch.setattr(op, "get_context", MagicMock(return_value=migration_context))
    return runpy.run_path(str(MIGRATION)), ddl


def _governed_definition() -> str:
    return (
        "CREATE INDEX ix_transactions_portfolio_transaction_id ON public.transactions "
        "USING btree (portfolio_id, transaction_id)"
    )


def test_upgrade_accepts_valid_governed_index(monkeypatch) -> None:
    migration, ddl = _load_migration(monkeypatch)
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        return_value=index_state(True, True, _governed_definition())
    )

    migration["upgrade"]()

    ddl.assert_not_called()


def test_upgrade_repairs_invalid_concurrent_index(monkeypatch) -> None:
    migration, ddl = _load_migration(monkeypatch)
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        return_value=index_state(False, False, _governed_definition())
    )

    migration["upgrade"]()

    assert ddl.mock_calls == [
        call.drop_index(
            INDEX_NAME,
            table_name="transactions",
            postgresql_concurrently=True,
            if_exists=True,
        ),
        call.create_index(
            INDEX_NAME,
            "transactions",
            ["portfolio_id", "transaction_id"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        ),
    ]


def test_upgrade_rejects_same_named_index_with_different_definition(monkeypatch) -> None:
    migration, ddl = _load_migration(monkeypatch)
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        return_value=index_state(
            True,
            True,
            "CREATE INDEX conflicting ON public.transactions USING btree (transaction_id)",
        )
    )

    with pytest.raises(RuntimeError, match="does not match the governed index definition"):
        migration["upgrade"]()

    ddl.assert_not_called()


def test_downgrade_refuses_to_drop_conflicting_same_named_index(monkeypatch) -> None:
    migration, ddl = _load_migration(monkeypatch)
    index_state = migration["_IndexState"]
    migration["downgrade"].__globals__["_index_state"] = MagicMock(
        return_value=index_state(
            True,
            True,
            "CREATE INDEX conflicting ON public.transactions USING btree (transaction_id)",
        )
    )

    with pytest.raises(RuntimeError, match="does not match the governed index definition"):
        migration["downgrade"]()

    ddl.assert_not_called()
