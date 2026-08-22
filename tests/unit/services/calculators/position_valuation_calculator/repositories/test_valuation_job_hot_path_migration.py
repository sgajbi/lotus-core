"""Executable contract for the valuation-job hot-path index migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[6]
    / "alembic"
    / "versions"
    / "c160b2c3d527_perf_bound_valuation_job_hot_paths.py"
)


def test_valuation_job_hot_path_index_migration_is_reversible(monkeypatch) -> None:
    create_index = MagicMock()
    drop_index = MagicMock()
    migration_context = MagicMock()
    migration_context.as_sql = False
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    monkeypatch.setattr(op, "get_context", MagicMock(return_value=migration_context))
    migration = runpy.run_path(str(MIGRATION))
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        side_effect=[
            None,
            index_state(
                True,
                True,
                "CREATE INDEX old ON public.portfolio_valuation_jobs USING btree "
                "(valuation_lease_expires_at) "
                "WHERE ((status)::text = 'PROCESSING'::text)",
            ),
        ]
    )

    migration["upgrade"]()
    migration["downgrade"].__globals__["_index_state"] = MagicMock(
        side_effect=[
            None,
            index_state(
                True,
                True,
                "CREATE INDEX new ON public.portfolio_valuation_jobs USING btree "
                "(valuation_lease_expires_at, id) "
                "WHERE ((status)::text = 'PROCESSING'::text)",
            ),
        ]
    )
    migration["downgrade"]()

    assert [call.args[:3] for call in create_index.call_args_list] == [
        (
            "ix_portfolio_valuation_jobs_processing_lease_recovery",
            "portfolio_valuation_jobs",
            ["valuation_lease_expires_at", "id"],
        ),
        (
            "ix_portfolio_valuation_jobs_processing_lease_expiry",
            "portfolio_valuation_jobs",
            ["valuation_lease_expires_at"],
        ),
    ]
    assert all(
        str(call.kwargs["postgresql_where"]) == "status = 'PROCESSING'"
        for call in create_index.call_args_list
    )
    assert all(call.kwargs["postgresql_concurrently"] for call in create_index.call_args_list)
    assert all(call.kwargs["if_not_exists"] for call in create_index.call_args_list)
    assert [call.args for call in drop_index.call_args_list] == [
        ("ix_portfolio_valuation_jobs_processing_lease_expiry",),
        ("ix_portfolio_valuation_jobs_processing_lease_recovery",),
    ]
    assert all(
        call.kwargs["table_name"] == "portfolio_valuation_jobs"
        for call in drop_index.call_args_list
    )
    assert all(call.kwargs["postgresql_concurrently"] for call in drop_index.call_args_list)
    assert all(call.kwargs["if_exists"] for call in drop_index.call_args_list)
    assert migration_context.autocommit_block.call_count == 2


def test_upgrade_resumes_valid_partial_replacement(monkeypatch) -> None:
    create_index = MagicMock()
    drop_index = MagicMock()
    migration_context = MagicMock()
    migration_context.as_sql = False
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    monkeypatch.setattr(op, "get_context", MagicMock(return_value=migration_context))
    migration = runpy.run_path(str(MIGRATION))
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        side_effect=[
            index_state(
                True,
                True,
                "CREATE INDEX governed ON public.portfolio_valuation_jobs USING btree "
                "(valuation_lease_expires_at, id) "
                "WHERE ((status)::text = 'PROCESSING'::text)",
            ),
            index_state(
                True,
                True,
                "CREATE INDEX old ON public.portfolio_valuation_jobs USING btree "
                "(valuation_lease_expires_at) "
                "WHERE ((status)::text = 'PROCESSING'::text)",
            ),
        ]
    )

    migration["upgrade"]()

    create_index.assert_not_called()
    drop_index.assert_called_once_with(
        "ix_portfolio_valuation_jobs_processing_lease_expiry",
        table_name="portfolio_valuation_jobs",
        postgresql_concurrently=True,
        if_exists=True,
    )


def test_upgrade_repairs_invalid_concurrent_index(monkeypatch) -> None:
    ddl = MagicMock()
    migration_context = MagicMock()
    migration_context.as_sql = False
    monkeypatch.setattr(op, "create_index", ddl.create_index)
    monkeypatch.setattr(op, "drop_index", ddl.drop_index)
    monkeypatch.setattr(op, "get_context", MagicMock(return_value=migration_context))
    migration = runpy.run_path(str(MIGRATION))
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        side_effect=[
            index_state(False, False, "invalid"),
            index_state(
                True,
                True,
                "CREATE INDEX old ON public.portfolio_valuation_jobs USING btree "
                "(valuation_lease_expires_at) "
                "WHERE ((status)::text = 'PROCESSING'::text)",
            ),
        ]
    )

    migration["upgrade"]()

    assert ddl.mock_calls == [
        call.drop_index(
            "ix_portfolio_valuation_jobs_processing_lease_recovery",
            table_name="portfolio_valuation_jobs",
            postgresql_concurrently=True,
            if_exists=True,
        ),
        call.create_index(
            "ix_portfolio_valuation_jobs_processing_lease_recovery",
            "portfolio_valuation_jobs",
            ["valuation_lease_expires_at", "id"],
            postgresql_where=migration["_PROCESSING_PREDICATE"],
            postgresql_concurrently=True,
            if_not_exists=True,
        ),
        call.drop_index(
            "ix_portfolio_valuation_jobs_processing_lease_expiry",
            table_name="portfolio_valuation_jobs",
            postgresql_concurrently=True,
            if_exists=True,
        ),
    ]


def test_upgrade_rejects_conflicting_existing_index(monkeypatch) -> None:
    create_index = MagicMock()
    drop_index = MagicMock()
    migration_context = MagicMock()
    migration_context.as_sql = False
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    monkeypatch.setattr(op, "get_context", MagicMock(return_value=migration_context))
    migration = runpy.run_path(str(MIGRATION))
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        return_value=index_state(
            True,
            True,
            "CREATE INDEX conflicting ON public.portfolio_valuation_jobs USING btree (id)",
        )
    )

    with pytest.raises(RuntimeError, match="does not match the governed index definition"):
        migration["upgrade"]()

    create_index.assert_not_called()
    drop_index.assert_not_called()


def test_upgrade_rejects_conflicting_superseded_index(monkeypatch) -> None:
    create_index = MagicMock()
    drop_index = MagicMock()
    migration_context = MagicMock()
    migration_context.as_sql = False
    monkeypatch.setattr(op, "create_index", create_index)
    monkeypatch.setattr(op, "drop_index", drop_index)
    monkeypatch.setattr(op, "get_context", MagicMock(return_value=migration_context))
    migration = runpy.run_path(str(MIGRATION))
    index_state = migration["_IndexState"]
    migration["upgrade"].__globals__["_index_state"] = MagicMock(
        side_effect=[
            index_state(
                True,
                True,
                "CREATE INDEX new ON public.portfolio_valuation_jobs USING btree "
                "(valuation_lease_expires_at, id) "
                "WHERE ((status)::text = 'PROCESSING'::text)",
            ),
            index_state(
                True,
                True,
                "CREATE INDEX conflicting ON public.portfolio_valuation_jobs USING btree (id)",
            ),
        ]
    )

    with pytest.raises(RuntimeError, match="does not match the governed index definition"):
        migration["upgrade"]()

    create_index.assert_not_called()
    drop_index.assert_not_called()
