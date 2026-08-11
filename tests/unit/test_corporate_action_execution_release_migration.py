"""Executable contract for the corporate-action execution-release migration."""

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
    / "c153b2c3d520_feat_add_corporate_action_execution_releases.py"
)


def test_execution_release_migration_is_fenced_ordered_and_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "drop_table",
        lambda name: operations.append(("drop_table", name)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c153b2c3d520"
    assert migration["down_revision"] == "c152b2c3d519"
    assert operations[0][0:2] == (
        "add_column",
        "corporate_action_child_observations",
    )
    assert (
        "create_check_constraint",
        "ck_ca_observation_transaction_fingerprint",
        "corporate_action_child_observations",
        "transaction_payload_fingerprint IS NULL OR "
        "transaction_payload_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
    ) in operations
    assert [operation[1] for operation in operations if operation[0] == "create_table"] == [
        "corporate_action_execution_releases",
        "corporate_action_execution_members",
    ]
    assert [operation[1] for operation in operations if operation[0] == "drop_table"] == [
        "corporate_action_execution_members",
        "corporate_action_execution_releases",
    ]

    created_indexes = {
        operation[1]: (operation[2], operation[3])
        for operation in operations
        if operation[0] == "create_index"
    }
    assert created_indexes == {
        "ix_ca_execution_release_claim": (
            "corporate_action_execution_releases",
            ["status", "lease_expires_at", "id"],
        ),
        "ix_ca_execution_member_pending": (
            "corporate_action_execution_members",
            ["release_id", "status", "execution_ordinal"],
        ),
        "ix_ca_execution_member_transaction": (
            "corporate_action_execution_members",
            ["transaction_id"],
        ),
    }

    sql = "\n".join(str(operation[1]) for operation in operations if operation[0] == "execute")
    for invariant in (
        "corporate-action execution release authority is immutable",
        "corporate-action execution release progress is monotonic",
        "corporate-action execution terminal state is immutable",
        "corporate-action execution member authority is immutable",
        "corporate-action execution member completion is immutable",
        "corporate-action execution release lacks current READY authority",
        "corporate-action execution member lacks exact observation authority",
        "corporate-action execution member progress is not a complete prefix",
        "corporate-action execution release hash is not canonical",
    ):
        assert invariant in sql
    assert "BEFORE UPDATE OR DELETE ON corporate_action_execution_releases" in sql
    assert "BEFORE UPDATE OR DELETE ON corporate_action_execution_members" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "AFTER UPDATE ON corporate_action_execution_members" in sql
    assert (
        "AFTER INSERT OR UPDATE ON corporate_action_execution_releases\n"
        "            DEFERRABLE INITIALLY DEFERRED\n"
        "            FOR EACH ROW\n"
        "            EXECUTE FUNCTION enforce_ca_execution_release_authority()"
    ) in sql
    assert (
        "AFTER UPDATE ON corporate_action_execution_members\n"
        "            DEFERRABLE INITIALLY DEFERRED\n"
        "            FOR EACH ROW\n"
        "            EXECUTE FUNCTION enforce_ca_execution_member_progress()"
    ) in sql
    assert "DROP FUNCTION enforce_ca_execution_release_authority() CASCADE" in sql
    assert "DROP FUNCTION enforce_ca_execution_member_progress() CASCADE" in sql
    assert "DROP FUNCTION validate_ca_execution_release(bigint) CASCADE" in sql
    assert "DROP FUNCTION enforce_ca_execution_member_authority() CASCADE" in sql
    assert "DROP FUNCTION enforce_ca_execution_release_ready_insert() CASCADE" in sql
    assert "DROP FUNCTION enforce_ca_execution_member_identity() CASCADE" in sql
    assert "DROP FUNCTION enforce_ca_execution_release_identity() CASCADE" in sql
    assert (
        "drop_constraint",
        "ck_ca_observation_transaction_fingerprint",
        "corporate_action_child_observations",
        {"type_": "check"},
    ) in operations
    assert (
        "drop_column",
        "corporate_action_child_observations",
        "transaction_payload_fingerprint",
    ) in operations
