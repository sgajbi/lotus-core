"""Fail-closed ranking for versioned financial source records."""

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

    versions_by_source: dict[_SourceRecordKey, dict[int, _SourceRecord]] = {}
    for record in records:
        key = source_record_key(record)
        version = source_version(record)
        versions = versions_by_source.setdefault(key, {})
        existing = versions.get(version)
        if existing is not None and record != existing:
            raise conflicting_version_error()
        versions[version] = record
    return [versions[max(versions)] for versions in versions_by_source.values()]
