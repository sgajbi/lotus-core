"""Shared fail-closed ranking for versioned financial source records."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from typing import TypeVar

_SourceRecord = TypeVar("_SourceRecord")
_SourceRecordKey = TypeVar("_SourceRecordKey", bound=Hashable)


def latest_source_versions(
    records: Iterable[_SourceRecord],
    *,
    source_record_key: Callable[[_SourceRecord], _SourceRecordKey],
    source_version: Callable[[_SourceRecord], int],
    conflicting_version_error: Callable[[], Exception],
) -> list[_SourceRecord]:
    """Keep the latest correction per source identity and reject ambiguous versions."""

    latest: dict[_SourceRecordKey, _SourceRecord] = {}
    for record in records:
        key = source_record_key(record)
        existing = latest.get(key)
        if existing is None or source_version(record) > source_version(existing):
            latest[key] = record
        elif source_version(record) == source_version(existing) and record != existing:
            raise conflicting_version_error()
    return list(latest.values())
