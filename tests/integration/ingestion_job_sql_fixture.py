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


def transaction_payload_evidence_insert_fragments(connection: Connection) -> tuple[str, str]:
    """Return complete c157 transaction-evidence fragments when that schema is present."""

    table_columns = {column["name"] for column in inspect(connection).get_columns("ingestion_jobs")}
    present_columns = set(_PAYLOAD_EVIDENCE_COLUMNS) & table_columns
    if not present_columns:
        return "", ""
    if present_columns != set(_PAYLOAD_EVIDENCE_COLUMNS):
        missing = sorted(set(_PAYLOAD_EVIDENCE_COLUMNS) - present_columns)
        raise AssertionError(f"ingestion payload evidence schema is incomplete: {missing}")

    columns = ",\n" + ",\n".join(_PAYLOAD_EVIDENCE_COLUMNS)
    values = """,
'ingestion-evidence-policy.v1',
'restricted',
'fingerprint_only',
false,
false,
NULL,
'lotus-core#708'"""
    return columns, values
