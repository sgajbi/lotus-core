"""Executable contract for the corporate-action parent-graph migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c152b2c3d519_feat_add_corporate_action_event_graph.py"
)


def test_parent_graph_migration_is_ordered_constrained_and_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "execute",
        lambda statement: operations.append(("execute", str(statement))),
    )
    monkeypatch.setattr(
        op,
        "create_table",
        lambda name, *elements, **kwargs: operations.append(
            ("create_table", name, elements, kwargs)
        ),
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
        "create_foreign_key",
        lambda name, source, referent, local, remote, **kwargs: operations.append(
            ("create_foreign_key", name, source, referent, local, remote, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_table",
        lambda name: operations.append(("drop_table", name)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c152b2c3d519"
    assert migration["down_revision"] == "c151b2c3d518"

    created_tables = [operation[1] for operation in operations if operation[0] == "create_table"]
    assert created_tables == [
        "corporate_action_events",
        "corporate_action_manifest_versions",
        "corporate_action_manifest_nodes",
        "corporate_action_manifest_edges",
        "corporate_action_child_observations",
        "corporate_action_readiness_evaluations",
    ]
    assert [operation[1] for operation in operations if operation[0] == "drop_table"] == [
        "corporate_action_readiness_evaluations",
        "corporate_action_child_observations",
        "corporate_action_manifest_edges",
        "corporate_action_manifest_nodes",
        "corporate_action_manifest_versions",
        "corporate_action_events",
    ]

    sql = "\n".join(str(operation[1]) for operation in operations if operation[0] == "execute")
    for invariant in (
        "corporate-action ledger rows are immutable",
        "corporate-action event identity is immutable",
        "corporate-action manifest predecessor does not continue the event chain",
        "corporate-action manifest opening boundary does not match event state",
        "corporate-action observation transaction is outside event portfolio",
        "corporate-action READY plan does not match manifest node order",
        "corporate-action READY plan does not match manifest edges",
        "corporate-action READY evidence does not match complete manifest",
        "corporate-action READY evidence is stale against event state",
        "corporate-action READY evidence does not match latest child observations",
        "unexpected_observation_count",
        "ca_observation_is_authorized",
        "retained_manifest_chain",
    ):
        assert invariant in sql
    assert "'parent_event_reference', 'portfolio_id', 'source_reference', 'version'" in sql
    assert "manifest.manifest_payload ->> 'tenant_id' = event.tenant_id" not in sql
    assert "manifest.manifest_payload ->> 'legal_book_id' = event.legal_book_id" not in sql

    immutable_ledgers = {
        "corporate_action_manifest_versions": "manifest_version",
        "corporate_action_manifest_nodes": "manifest_node",
        "corporate_action_manifest_edges": "manifest_edge",
        "corporate_action_child_observations": "child_observation",
        "corporate_action_readiness_evaluations": "readiness_evaluation",
    }
    for table, suffix in immutable_ledgers.items():
        assert f"CREATE TRIGGER trg_ca_{suffix}_immutable" in sql
        assert f"BEFORE UPDATE OR DELETE ON {table}" in sql

    assert (
        "create_foreign_key",
        "fk_ca_event_current_manifest",
        "corporate_action_events",
        "corporate_action_manifest_versions",
        ["id", "current_manifest_version"],
        ["event_id", "manifest_version"],
        {},
    ) in operations
    assert (
        "drop_constraint",
        "fk_ca_event_current_manifest",
        "corporate_action_events",
        {"type_": "foreignkey"},
    ) in operations

    readiness_drop = operations.index(("drop_table", "corporate_action_readiness_evaluations"))
    event_drop = operations.index(("drop_table", "corporate_action_events"))
    assert readiness_drop < event_drop
    assert "DROP FUNCTION reject_ca_ledger_mutation()" in sql
