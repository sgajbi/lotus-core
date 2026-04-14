"""RFC-0083 market and reference data quality helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from portfolio_common.reconciliation_quality import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    STALE,
    UNKNOWN,
    DataQualityCoverageSignal,
    classify_data_quality_coverage,
)


ACCEPTED_QUALITY_STATUSES = {"ACCEPTED"}
PARTIAL_QUALITY_STATUSES = {"ESTIMATED", "PROVISIONAL", "WARNING"}
STALE_QUALITY_STATUSES = {"STALE"}
BLOCKING_QUALITY_STATUSES = {"REJECTED", "QUARANTINED", "INVALID", "BLOCKED"}


@dataclass(frozen=True)
class SourceObservationSignal:
    observed_at: datetime | None = None
    source_timestamp: datetime | None = None
    ingested_at: datetime | None = None


@dataclass(frozen=True)
class MarketReferencePointSignal:
    quality_status: str | None
    observed_at: datetime | None = None
    source_timestamp: datetime | None = None
    ingested_at: datetime | None = None
    is_stale: bool = False


@dataclass(frozen=True)
class MarketReferenceCoverageSignal:
    required_count: int
    observed_count: int
    stale_count: int = 0
    estimated_count: int = 0
    blocking_count: int = 0


def resolve_observed_at(signal: SourceObservationSignal) -> datetime | None:
    """Return canonical observed_at, mapping legacy source_timestamp when needed."""

    observed_at = _datetime_or_none(signal.observed_at, "observed_at")
    source_timestamp = _datetime_or_none(signal.source_timestamp, "source_timestamp")
    _datetime_or_none(signal.ingested_at, "ingested_at")
    return observed_at or source_timestamp


def classify_market_reference_point(signal: MarketReferencePointSignal) -> str:
    observed_at = resolve_observed_at(
        SourceObservationSignal(
            observed_at=signal.observed_at,
            source_timestamp=signal.source_timestamp,
            ingested_at=signal.ingested_at,
        )
    )
    quality_status = _normalize_optional_text(signal.quality_status)
    if quality_status is None:
        return UNKNOWN
    if quality_status in BLOCKING_QUALITY_STATUSES:
        return BLOCKED
    if signal.is_stale or quality_status in STALE_QUALITY_STATUSES:
        return STALE
    if observed_at is None:
        return UNKNOWN
    if quality_status in PARTIAL_QUALITY_STATUSES:
        return PARTIAL
    if quality_status in ACCEPTED_QUALITY_STATUSES:
        return COMPLETE
    return UNKNOWN


def classify_market_reference_coverage(signal: MarketReferenceCoverageSignal) -> str:
    _require_non_negative(signal.estimated_count, "estimated_count")
    return classify_data_quality_coverage(
        DataQualityCoverageSignal(
            required_count=signal.required_count,
            observed_count=signal.observed_count,
            stale_count=signal.stale_count,
            blocking_issue_count=signal.blocking_count,
            warning_issue_count=signal.estimated_count,
        )
    )


def summarize_quality_statuses(statuses: tuple[str | None, ...]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for status in statuses:
        normalized = _normalize_optional_text(status) or UNKNOWN.lower()
        key = normalized.lower()
        summary[key] = summary.get(key, 0) + 1
    return dict(sorted(summary.items()))


def _datetime_or_none(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
