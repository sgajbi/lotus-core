"""Executable contract proof for the reprocessing payload integrity cutover."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c162b2c3d529_fix_harden_reprocessing_payload_integrity.py"
)


def test_reprocessing_payload_integrity_migration_is_linear_guarded_and_reversible(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(op, "execute", lambda statement: operations.append(("execute", statement)))
    monkeypatch.setattr(
        op,
        "alter_column",
        lambda table, column, **kwargs: operations.append(
            ("alter_column", table, column, kwargs)
        ),
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
        lambda name, table, **kwargs: operations.append(
            ("drop_constraint", name, table, kwargs)
        ),
    )

    migration = runpy.run_path(str(MIGRATION))
    assert migration["revision"] == "c162b2c3d529"
    assert migration["down_revision"] == "c161b2c3d528"

    migration["upgrade"]()
    cutover = str(operations[0][1])
    assert "LOCK TABLE reprocessing_jobs IN ACCESS EXCLUSIVE MODE" in cutover
    assert "requires a drained PROCESSING queue" in cutover
    assert cutover.count("GET DIAGNOSTICS") == 2
    assert "RESET_FX_WATERMARKS" in cutover
    assert "RESET_WATERMARKS" in cutover
    assert "pg_input_is_valid" in cutover
    assert "quarantined during contract cutover" in cutover

    constraint = operations[1]
    assert constraint[:3] == (
        "create_check_constraint",
        "ck_reprocessing_jobs_active_payload_valid",
        "reprocessing_jobs",
    )
    assert "status NOT IN ('PENDING', 'PROCESSING')" in constraint[3]
    assert "RESET_FX_WATERMARKS" in constraint[3]
    assert "RESET_WATERMARKS" in constraint[3]
    assert "pg_input_is_valid" in constraint[3]
    assert constraint[3].count("IS TRUE") == 3

    operations.clear()
    migration["downgrade"]()
    assert operations[0][:3] == (
        "drop_constraint",
        "ck_reprocessing_jobs_active_payload_valid",
        "reprocessing_jobs",
    )
