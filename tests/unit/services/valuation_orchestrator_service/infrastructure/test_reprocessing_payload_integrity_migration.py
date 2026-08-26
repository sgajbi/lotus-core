"""Executable contract proof for the reprocessing payload integrity cutover."""

from __future__ import annotations

import runpy
from pathlib import Path

from portfolio_common.database_models import ReprocessingJob

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c162b2c3d529_fix_harden_reprocessing_payload_integrity.py"
)


def _normalized_sql(value: object) -> str:
    return " ".join(str(value).split())


def test_reprocessing_payload_integrity_migration_is_linear_guarded_and_reversible(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(op, "execute", lambda statement: operations.append(("execute", statement)))
    monkeypatch.setattr(
        op,
        "alter_column",
        lambda table, column, **kwargs: operations.append(("alter_column", table, column, kwargs)),
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

    migration = runpy.run_path(str(MIGRATION))
    assert migration["revision"] == "c162b2c3d529"
    assert migration["down_revision"] == "c161b2c3d528"

    migration["upgrade"]()
    cutover = str(operations[0][1])
    assert "LOCK TABLE reprocessing_jobs IN ACCESS EXCLUSIVE MODE" in cutover
    assert "requires a drained PROCESSING queue" in cutover
    assert "status IN ('PENDING', 'PROCESSING')" in cutover
    assert "pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE" in cutover
    assert "active row(s) that cannot" in cutover
    assert "terminalize or repair" in cutover
    assert cutover.index("pg_input_is_valid(payload::text") < cutover.index("requires a drained")
    assert cutover.index("pg_input_is_valid(payload::text") < cutover.index(
        "payload->>'from_currency'"
    )
    assert cutover.count("GET DIAGNOSTICS") == 2
    assert "RESET_FX_WATERMARKS" in cutover
    assert "RESET_WATERMARKS" in cutover
    assert "pg_input_is_valid" in cutover
    assert cutover.count("jsonb_typeof") == 7
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
    assert constraint[3].count("jsonb_typeof") == 7
    assert "CASE" in constraint[3]
    assert "^[0-9]" not in constraint[3]
    model_constraint = next(
        item
        for item in ReprocessingJob.__table__.constraints
        if item.name == "ck_reprocessing_jobs_active_payload_valid"
    )
    assert _normalized_sql(constraint[3]) == _normalized_sql(model_constraint.sqltext)

    operations.clear()
    migration["downgrade"]()
    assert operations[0][:3] == (
        "drop_constraint",
        "ck_reprocessing_jobs_active_payload_valid",
        "reprocessing_jobs",
    )
