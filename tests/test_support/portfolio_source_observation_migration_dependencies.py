"""Exercise real observation migration dependencies in historical schema proofs."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/c178b2c3d539_add_portfolio_source_observations.py"
)
_IDENTITY = ["tenant_id", "portfolio_id", "producer_id", "source_record_id"]
_FAMILIES = ("cash_availability", "funding_investment")


def observation_schema_semantics(connection: Connection) -> tuple:
    """Validate all four tables' authority/guards and capture exact catalog semantics."""
    inspector = inspect(connection)
    semantics = []
    for family in _FAMILIES:
        fact = f"portfolio_{family}_observations"
        head = f"portfolio_{family}_observation_heads"
        for table, expected in (
            (
                fact,
                [
                    (["tenant_id", "portfolio_id"], "portfolios", ["tenant_id", "portfolio_id"]),
                    (["tenant_id", "receipt_job_id"], "ingestion_jobs", ["tenant_id", "job_id"]),
                    (
                        [*_IDENTITY, "predecessor_id", "expected_head_hash"],
                        fact,
                        [*_IDENTITY, "observation_id", "content_hash"],
                    ),
                ],
            ),
            (
                head,
                [
                    (
                        [*_IDENTITY, "observation_id", "content_hash"],
                        fact,
                        [*_IDENTITY, "observation_id", "content_hash"],
                    )
                ],
            ),
        ):
            assert inspector.has_table(table, schema="public")
            foreign_keys = inspector.get_foreign_keys(table, schema="public")
            assert len(foreign_keys) == len(expected)
            for constrained, referred_table, referred in expected:
                matches = [key for key in foreign_keys if key["constrained_columns"] == constrained]
                assert len(matches) == 1
                key = matches[0]
                assert key["referred_schema"] == "public"
                assert key["referred_table"] == referred_table
                assert key["referred_columns"] == referred
                assert key["options"] == {}
            constraints = tuple(
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid), convalidated "
                        "FROM pg_constraint "
                        "WHERE conrelid = to_regclass(:table) AND contype = 'f' ORDER BY conname"
                    ),
                    {"table": f"public.{table}"},
                )
            )
            assert len(constraints) == len(expected) and all(row[2] for row in constraints)
            triggers = tuple(
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT t.tgname, t.tgtype, t.tgenabled, pn.nspname, p.proname, "
                        "pg_get_triggerdef(t.oid), pg_get_functiondef(p.oid) "
                        "FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid "
                        "JOIN pg_namespace pn ON pn.oid=p.pronamespace "
                        "WHERE t.tgrelid=to_regclass(:table) AND NOT t.tgisinternal "
                        "ORDER BY t.tgname"
                    ),
                    {"table": f"public.{table}"},
                )
            )
            expected_triggers = {
                f"{table}_no_truncate": (34, "guard_empty_portfolio_source_observation_truncate")
            }
            if table == fact:
                expected_triggers[f"{table}_immutable"] = (
                    27,
                    "reject_portfolio_source_observation_mutation",
                )
            assert len(triggers) == len(expected_triggers)
            for name, kind, enabled, schema, function, _definition, body in triggers:
                assert (kind, function) == expected_triggers[name]
                assert enabled == "O" and schema == "public"
                if kind == 34:
                    assert "read committed" in body
                    assert "nonempty portfolio source observations cannot be truncated" in body
                else:
                    assert "immutable" in body
            semantics.append((table, constraints, triggers))
    return tuple(semantics)


def downgrade_observation_schema(connection: Connection) -> dict[str, Any]:
    """Descend through the real isolation/lock/empty-history refusal, never drop FKs."""
    migration = runpy.run_path(str(_MIGRATION))
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations
    migration["downgrade"]()
    return migration


def restore_observation_schema(migration: dict[str, Any], connection: Connection) -> None:
    """Restore the real latest revision after its historical dependencies are upgraded."""
    migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    migration["upgrade"]()
