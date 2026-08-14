"""Decision-table proof for schema-aware ingestion-job migration fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.integration import ingestion_job_sql_fixture as fixture_sql


class _Inspector:
    def __init__(self, columns: tuple[str, ...]) -> None:
        self._columns = columns

    def get_columns(self, table_name: str) -> list[dict[str, str]]:
        assert table_name == "ingestion_jobs"
        return [{"name": column} for column in self._columns]


def _inspect_with(columns: tuple[str, ...]) -> Callable[[object], _Inspector]:
    return lambda connection: _Inspector(columns)


def test_legacy_ingestion_job_fixture_omits_absent_evidence_schema(monkeypatch) -> None:
    monkeypatch.setattr(fixture_sql, "inspect", _inspect_with(("job_id", "endpoint")))

    assert fixture_sql.transaction_payload_evidence_insert_fragments(object()) == ("", "")


def test_current_ingestion_job_fixture_declares_complete_fail_closed_policy(monkeypatch) -> None:
    monkeypatch.setattr(
        fixture_sql,
        "inspect",
        _inspect_with(("job_id", *fixture_sql._PAYLOAD_EVIDENCE_COLUMNS)),
    )

    columns, values = fixture_sql.transaction_payload_evidence_insert_fragments(object())

    assert all(column in columns for column in fixture_sql._PAYLOAD_EVIDENCE_COLUMNS)
    assert "ingestion-evidence-policy.v1" in values
    assert "restricted" in values
    assert "fingerprint_only" in values
    assert values.count("false") == 2
    assert "lotus-core#708" in values


def test_ingestion_job_fixture_rejects_partial_evidence_schema(monkeypatch) -> None:
    monkeypatch.setattr(
        fixture_sql,
        "inspect",
        _inspect_with(("job_id", fixture_sql._PAYLOAD_EVIDENCE_COLUMNS[0])),
    )

    with pytest.raises(AssertionError, match="ingestion payload evidence schema is incomplete"):
        fixture_sql.transaction_payload_evidence_insert_fragments(object())
