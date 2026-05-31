from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from portfolio_common.market_reference_quality import (
    BLOCKING_QUALITY_STATUSES,
    PARTIAL_QUALITY_STATUSES,
    STALE_QUALITY_STATUSES,
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
)

from ..dtos.reference_integration_dto import CoverageResponse
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata


def _date_range(start_date: date, end_date: date) -> set[date]:
    dates: set[date] = set()
    cursor = start_date
    while cursor <= end_date:
        dates.add(cursor)
        cursor = cursor + timedelta(days=1)
    return dates


def _observed_dates(coverage: dict[str, Any]) -> set[date]:
    observed_dates = {
        value for value in coverage.get("observed_dates", []) if isinstance(value, date)
    }
    if observed_dates:
        return observed_dates

    observed_start = coverage.get("observed_start_date")
    observed_end = coverage.get("observed_end_date")
    if not isinstance(observed_start, date) or not isinstance(observed_end, date):
        return set()
    return _date_range(observed_start, observed_end)


def market_reference_coverage_response(
    *,
    coverage: dict[str, Any],
    start_date: date,
    end_date: date,
    request_fingerprint: str,
) -> CoverageResponse:
    expected_dates = _date_range(start_date, end_date)
    observed_dates = _observed_dates(coverage)
    missing_dates = sorted(expected_dates - observed_dates)

    quality_counts = dict(coverage.get("quality_status_counts", {}))
    normalized_quality_counts = {
        str(status).strip().upper(): int(count) for status, count in quality_counts.items() if count
    }
    data_quality_status = classify_market_reference_coverage(
        MarketReferenceCoverageSignal(
            required_count=len(expected_dates),
            observed_count=len(observed_dates),
            stale_count=sum(
                count
                for status, count in normalized_quality_counts.items()
                if status in STALE_QUALITY_STATUSES
            ),
            estimated_count=sum(
                count
                for status, count in normalized_quality_counts.items()
                if status in PARTIAL_QUALITY_STATUSES
            ),
            blocking_count=sum(
                count
                for status, count in normalized_quality_counts.items()
                if status in BLOCKING_QUALITY_STATUSES
            ),
        )
    )

    return CoverageResponse(
        request_fingerprint=request_fingerprint,
        observed_start_date=coverage.get("observed_start_date"),
        observed_end_date=coverage.get("observed_end_date"),
        expected_start_date=start_date,
        expected_end_date=end_date,
        total_points=int(coverage.get("total_points", 0)),
        missing_dates_count=len(missing_dates),
        missing_dates_sample=missing_dates[:10],
        quality_status_distribution=quality_counts,
        **source_data_product_runtime_metadata(
            as_of_date=end_date,
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=coverage.get("latest_evidence_timestamp"),
        ),
    )
