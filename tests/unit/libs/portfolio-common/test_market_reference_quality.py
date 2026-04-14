from datetime import UTC, datetime, timedelta, timezone

import pytest
from portfolio_common.market_reference_quality import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    STALE,
    UNKNOWN,
    MarketReferenceCoverageSignal,
    MarketReferencePointSignal,
    SourceObservationSignal,
    classify_market_reference_coverage,
    classify_market_reference_point,
    resolve_observed_at,
    summarize_quality_statuses,
)
from portfolio_common.reconciliation_quality import UNRECONCILED


def aware(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def test_resolve_observed_at_prefers_canonical_observed_at() -> None:
    observed_at = aware("2026-04-15T01:00:00")
    source_timestamp = observed_at - timedelta(hours=2)

    assert (
        resolve_observed_at(
            SourceObservationSignal(observed_at=observed_at, source_timestamp=source_timestamp)
        )
        == observed_at
    )


def test_resolve_observed_at_maps_legacy_source_timestamp_to_utc_observed_time() -> None:
    source_timestamp = datetime(2026, 4, 15, 9, 0, tzinfo=timezone(timedelta(hours=8)))

    assert resolve_observed_at(SourceObservationSignal(source_timestamp=source_timestamp)) == aware(
        "2026-04-15T01:00:00"
    )


def test_resolve_observed_at_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="source_timestamp must be timezone-aware"):
        resolve_observed_at(SourceObservationSignal(source_timestamp=datetime(2026, 4, 15, 9, 0)))


@pytest.mark.parametrize(
    ("signal", "expected"),
    [
        (
            MarketReferencePointSignal(
                quality_status="accepted", observed_at=aware("2026-04-15T01:00:00")
            ),
            COMPLETE,
        ),
        (
            MarketReferencePointSignal(
                quality_status="estimated", observed_at=aware("2026-04-15T01:00:00")
            ),
            PARTIAL,
        ),
        (
            MarketReferencePointSignal(
                quality_status="accepted", observed_at=aware("2026-04-15T01:00:00"), is_stale=True
            ),
            STALE,
        ),
        (
            MarketReferencePointSignal(
                quality_status="rejected", observed_at=aware("2026-04-15T01:00:00")
            ),
            BLOCKED,
        ),
        (MarketReferencePointSignal(quality_status="accepted"), UNKNOWN),
        (MarketReferencePointSignal(quality_status=None), UNKNOWN),
    ],
)
def test_classify_market_reference_point(signal, expected) -> None:
    assert classify_market_reference_point(signal) == expected


@pytest.mark.parametrize(
    ("signal", "expected"),
    [
        (MarketReferenceCoverageSignal(required_count=10, observed_count=10), COMPLETE),
        (MarketReferenceCoverageSignal(required_count=10, observed_count=8), PARTIAL),
        (
            MarketReferenceCoverageSignal(required_count=10, observed_count=10, estimated_count=1),
            PARTIAL,
        ),
        (MarketReferenceCoverageSignal(required_count=10, observed_count=10, stale_count=1), STALE),
        (
            MarketReferenceCoverageSignal(required_count=10, observed_count=10, blocking_count=1),
            BLOCKED,
        ),
        (MarketReferenceCoverageSignal(required_count=10, observed_count=0), UNRECONCILED),
        (MarketReferenceCoverageSignal(required_count=0, observed_count=0), UNKNOWN),
    ],
)
def test_classify_market_reference_coverage(signal, expected) -> None:
    assert classify_market_reference_coverage(signal) == expected


def test_classify_market_reference_coverage_rejects_negative_estimated_count() -> None:
    with pytest.raises(ValueError, match="estimated_count must be non-negative"):
        classify_market_reference_coverage(
            MarketReferenceCoverageSignal(required_count=1, observed_count=1, estimated_count=-1)
        )


def test_summarize_quality_statuses_normalizes_and_sorts_counts() -> None:
    assert summarize_quality_statuses(("accepted", "ACCEPTED", " estimated ", None)) == {
        "accepted": 2,
        "estimated": 1,
        "unknown": 1,
    }
