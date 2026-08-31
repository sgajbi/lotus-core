"""Schema-aware SQL fragments for legacy ingestion-job migration fixtures."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Connection

_PAYLOAD_EVIDENCE_COLUMNS = (
    "request_payload_policy_version",
    "request_payload_classification",
    "request_payload_representation",
    "request_payload_replay_eligible",
    "request_payload_partial_replay_eligible",
    "request_payload_replay_expires_at",
    "request_payload_retention_authority",
)


def transaction_ingestion_job_insert_fragments(connection: Connection) -> tuple[str, str]:
    """Return required later-schema fragments for a transaction ingestion-job fixture."""

    table_columns = {column["name"] for column in inspect(connection).get_columns("ingestion_jobs")}
    columns: list[str] = []
    values: list[str] = []
    if "tenant_id" in table_columns:
        columns.append("tenant_id")
        values.append(":tenant_id")

    present_columns = set(_PAYLOAD_EVIDENCE_COLUMNS) & table_columns
    if not present_columns:
        return _insert_fragments(columns, values)
    if present_columns != set(_PAYLOAD_EVIDENCE_COLUMNS):
        missing = sorted(set(_PAYLOAD_EVIDENCE_COLUMNS) - present_columns)
        raise AssertionError(f"ingestion payload evidence schema is incomplete: {missing}")

    columns.extend(_PAYLOAD_EVIDENCE_COLUMNS)
    values.extend(
        (
            "'ingestion-evidence-policy.v1'",
            "'restricted'",
            "'fingerprint_only'",
            "false",
            "false",
            "NULL",
            "'lotus-core#708'",
        )
    )
    return _insert_fragments(columns, values)


def _insert_fragments(columns: list[str], values: list[str]) -> tuple[str, str]:
    if not columns:
        return "", ""
    return ",\n" + ",\n".join(columns), ",\n" + ",\n".join(values)
