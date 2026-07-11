"""Typed source-evidence timestamp policy shared by QCP source products."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol


class EvidenceTimestampRecord(Protocol):
    """Record fields that can establish latest source evidence."""

    @property
    def observed_at(self) -> datetime | None: ...

    @property
    def created_at(self) -> datetime | None: ...

    @property
    def updated_at(self) -> datetime | None: ...


def latest_evidence_timestamp(
    *record_groups: Sequence[EvidenceTimestampRecord],
) -> datetime | None:
    """Return the latest persisted or observed timestamp across typed records."""

    timestamps = [
        timestamp
        for records in record_groups
        for record in records
        for timestamp in (record.observed_at, record.updated_at, record.created_at)
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None
