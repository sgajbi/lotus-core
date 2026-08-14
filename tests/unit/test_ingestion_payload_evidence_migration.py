"""Executable contract proof for governed ingestion payload evidence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c157b2c3d524_feat_govern_ingestion_payload_evidence.py"
)
SCHEMA_CATALOG = (
    Path(__file__).resolve().parents[2] / "docs" / "data" / "database-schema-catalog.md"
)


def test_ingestion_job_schema_catalog_publishes_governed_evidence_columns() -> None:
    catalog = SCHEMA_CATALOG.read_text(encoding="utf-8")
    ingestion_jobs = catalog.split("## `ingestion_jobs`", maxsplit=1)[1].split(
        "## `ingestion_job_failures`", maxsplit=1
    )[0]

    for column in (
        "failure_status_code",
        "failure_code",
        "failure_detail",
        "failure_headers",
        "request_payload",
        "request_payload_fingerprint",
        "request_payload_policy_version",
        "request_payload_classification",
        "request_payload_representation",
        "request_payload_replay_eligible",
        "request_payload_partial_replay_eligible",
        "request_payload_replay_expires_at",
        "request_payload_retention_authority",
    ):
        assert f"`{column}`" in ingestion_jobs

    assert "does not authorize replay or reconstruct payload" in ingestion_jobs
    assert "SQL `NULL` for fingerprint-only evidence" in ingestion_jobs
    assert "Named governing retention decision" in ingestion_jobs


def test_ingestion_payload_evidence_migration_is_fail_closed_and_reversible(
    monkeypatch,
) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(
            ("add_column", table, column.name, str(column.type), column.nullable)
        ),
    )
    monkeypatch.setattr(
        op,
        "execute",
        lambda statement: operations.append(("execute", str(statement))),
    )
    monkeypatch.setattr(
        op,
        "alter_column",
        lambda table, column, **kwargs: operations.append(("alter_column", table, column, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition, **kwargs: operations.append(
            ("create_check", table, name, condition, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_check", table, name, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c157b2c3d524"
    assert migration["down_revision"] == "c156b2c3d523"
    added_columns = [operation[2] for operation in operations if operation[0] == "add_column"]
    assert added_columns == [
        "request_payload_policy_version",
        "request_payload_classification",
        "request_payload_representation",
        "request_payload_replay_eligible",
        "request_payload_partial_replay_eligible",
        "request_payload_replay_expires_at",
        "request_payload_retention_authority",
    ]
    execute_statements = [operation[1] for operation in operations if operation[0] == "execute"]
    normalization = next(
        statement for statement in execute_statements if "json_typeof(request_payload)" in statement
    )
    assert "json_typeof(failure_detail) = 'null'" in normalization
    assert "json_typeof(failure_headers) = 'null'" in normalization
    assert normalization.count("THEN NULL") == 3
    fingerprint_scrubs = [
        statement
        for statement in execute_statements
        if "SET request_payload_fingerprint = NULL" in statement
    ]
    assert fingerprint_scrubs == [
        "UPDATE ingestion_jobs SET request_payload_fingerprint = NULL",
        "UPDATE ingestion_jobs SET request_payload_fingerprint = NULL",
    ]
    downgrade_scrub_index = max(
        index
        for index, operation in enumerate(operations)
        if operation == ("execute", fingerprint_scrubs[-1])
    )
    first_drop_column_index = next(
        index for index, operation in enumerate(operations) if operation[0] == "drop_column"
    )
    assert downgrade_scrub_index < first_drop_column_index
    job_failure_scrub = next(
        statement
        for statement in execute_statements
        if "UPDATE ingestion_jobs" in statement and "historical_failure_reason" in statement
    )
    assert "failure_detail = NULL" in job_failure_scrub
    assert "failure_headers = NULL" in job_failure_scrub
    history_failure_scrub = next(
        statement
        for statement in execute_statements
        if "UPDATE ingestion_job_failures" in statement
    )
    assert "historical_failure_reason" in history_failure_scrub
    replay_failure_scrub = next(
        statement
        for statement in execute_statements
        if "UPDATE consumer_dlq_replay_audit" in statement
    )
    assert "historical_replay_failure_reason" in replay_failure_scrub
    assert (
        "WHERE replay_status IN ('failed', 'replayed_bookkeeping_failed')" in replay_failure_scrub
    )
    backfill = next(
        statement
        for statement in execute_statements
        if "ingestion-evidence-policy.legacy.v0" in statement
    )
    assert "request_payload = CASE" in backfill
    assert "ELSE NULL" in backfill
    assert "ingestion-evidence-policy.legacy.v0" in backfill
    assert "request_payload_replay_eligible = false" in backfill
    assert "request_payload_replay_expires_at = NULL" in backfill
    assert "lotus-core#708" in backfill
    altered_columns = [operation[2] for operation in operations if operation[0] == "alter_column"]
    assert altered_columns == [
        column for column in added_columns if not column.endswith("expires_at")
    ]
    checks = [operation for operation in operations if operation[0] == "create_check"]
    assert len(checks) == 8
    fingerprint_check = next(
        operation for operation in checks if operation[2].endswith("payload_fingerprint_format")
    )
    assert "hmac-sha256:v1:" in fingerprint_check[3]
    assert "^sha256:" not in fingerprint_check[3]
    assert all(operation[4] == {"postgresql_not_valid": True} for operation in checks)
    assert (
        sum(
            operation[0] == "execute" and "VALIDATE CONSTRAINT" in operation[1]
            for operation in operations
        )
        == 8
    )
    assert [operation[2] for operation in operations if operation[0] == "drop_column"] == list(
        reversed(added_columns)
    )
