"""Executable contract proof for the reprocessing-job lease migration."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c161b2c3d528_feat_add_reprocessing_job_leases.py"
)


def test_reprocessing_job_lease_migration_is_constrained_reversible_and_linear(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(op, "execute", lambda statement: operations.append(("execute", statement)))
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
        "create_index",
        lambda name, table, columns, **kwargs: operations.append(
            ("create_index", name, table, tuple(columns), kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
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

    migration = runpy.run_path(str(MIGRATION))
    assert migration["revision"] == "c161b2c3d528"
    assert migration["down_revision"] == "c160b2c3d527"

    migration["upgrade"]()
    assert operations[0][0] == "execute"
    cutover_guard = str(operations[0][1])
    assert "set_config('lock_timeout', '5s', true)" in cutover_guard
    assert "LOCK TABLE reprocessing_jobs IN ACCESS EXCLUSIVE MODE" in cutover_guard
    assert "requires a drained PROCESSING queue" in cutover_guard
    added_columns = [entry[2] for entry in operations if entry[0] == "add_column"]
    assert [column.name for column in added_columns] == [
        "lease_owner",
        "lease_token",
        "lease_expires_at",
    ]
    assert added_columns[1].type.length == 32
    assert all(column.nullable is True for column in added_columns)
    assert [entry[1] for entry in operations if entry[0] == "create_check_constraint"] == [
        "ck_reprocessing_jobs_processing_lease",
        "ck_reprocessing_jobs_lease_owner_normalized",
        "ck_reprocessing_jobs_lease_token",
    ]
    assert [entry[1] for entry in operations if entry[0] == "create_index"] == [
        "ix_reprocessing_jobs_processing_lease_recovery"
    ]

    operations.clear()
    migration["downgrade"]()
    assert operations[0][0] == "execute"
    assert [entry[1] for entry in operations if entry[0] == "drop_index"] == [
        "ix_reprocessing_jobs_processing_lease_recovery"
    ]
    assert [entry[1] for entry in operations if entry[0] == "drop_constraint"] == [
        "ck_reprocessing_jobs_lease_token",
        "ck_reprocessing_jobs_lease_owner_normalized",
        "ck_reprocessing_jobs_processing_lease",
    ]
    assert [entry[2] for entry in operations if entry[0] == "drop_column"] == [
        "lease_expires_at",
        "lease_token",
        "lease_owner",
    ]
