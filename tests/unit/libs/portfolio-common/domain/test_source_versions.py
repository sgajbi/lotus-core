"""Tests for generic fail-closed source-version ranking."""

from dataclasses import dataclass

import pytest
from portfolio_common.domain.source_versions import latest_source_versions


@dataclass(frozen=True)
class _SourceRecord:
    source_id: str
    version: int
    value: str


def _latest(records: list[_SourceRecord]) -> list[_SourceRecord]:
    return latest_source_versions(
        records,
        source_record_key=lambda record: record.source_id,
        source_version=lambda record: record.version,
        conflicting_version_error=lambda: ValueError("ambiguous source version"),
    )


def test_latest_source_versions_keeps_newest_correction_per_identity() -> None:
    latest = _latest(
        [
            _SourceRecord("A", 1, "old"),
            _SourceRecord("B", 1, "independent"),
            _SourceRecord("A", 2, "corrected"),
        ]
    )

    assert latest == [
        _SourceRecord("A", 2, "corrected"),
        _SourceRecord("B", 1, "independent"),
    ]


def test_latest_source_versions_accepts_identical_duplicate_delivery() -> None:
    record = _SourceRecord("A", 1, "same")

    assert _latest([record, record]) == [record]


def test_latest_source_versions_rejects_conflicting_same_version_payloads() -> None:
    with pytest.raises(ValueError, match="ambiguous source version"):
        _latest(
            [
                _SourceRecord("A", 1, "first"),
                _SourceRecord("A", 1, "conflict"),
            ]
        )
