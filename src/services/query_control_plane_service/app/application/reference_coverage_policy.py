"""Deterministic quality, completeness, and source-proof policy for coverage reports."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any, Protocol, cast

from portfolio_common.market_reference_quality import (
    BLOCKING_QUALITY_STATUSES,
    PARTIAL_QUALITY_STATUSES,
    STALE_QUALITY_STATUSES,
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
    quality_status_summary_key,
)
from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.reference_coverage import CoverageRequest, CoverageResponse
from ..domain.benchmark_definition import BenchmarkComponentEvidence
from ..domain.benchmark_return_series import BenchmarkReturnEvidence
from ..domain.index_series import IndexPriceEvidence


class QualityEvidence(Protocol):
    """Typed quality field shared by coverage source records."""

    @property
    def quality_status(self) -> str: ...


def build_coverage_response(
    *,
    coverage_kind: str,
    identifier_key: str,
    identifier_value: str,
    request: CoverageRequest,
    observed_dates: list[date],
    total_points: int,
    quality_rows: Sequence[QualityEvidence],
    latest_evidence: datetime | None,
    content_records: dict[str, Any],
    source_refs: list[str],
    generated_at: datetime,
) -> CoverageResponse:
    """Build deterministic source-owned coverage evidence."""

    fingerprint = cast(
        str,
        request_fingerprint(
            {
                "coverage_key": coverage_kind,
                identifier_key: identifier_value,
                "window": request.window.model_dump(mode="json"),
            }
        ),
    )
    missing_count, missing_sample = _missing_dates(
        start_date=request.window.start_date,
        end_date=request.window.end_date,
        observed_dates=set(observed_dates),
    )
    quality_distribution = _quality_distribution(quality_rows)
    quality_status = _coverage_quality_status(
        required_count=_expected_date_count(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        observed_count=len(observed_dates),
        quality_distribution=quality_distribution,
    )
    content_hash = cast(
        str,
        stable_content_hash(
            {
                "product_name": "DataQualityCoverageReport",
                "product_version": "v1",
                "coverage_kind": coverage_kind,
                identifier_key: identifier_value,
                "window": request.window.model_dump(mode="json"),
                "request_fingerprint": fingerprint,
                "observed_dates": observed_dates,
                "total_points": total_points,
                "quality_status_distribution": quality_distribution,
                "latest_evidence_timestamp": latest_evidence,
                "records": content_records,
            }
        ),
    )
    current = quality_status == "COMPLETE" and latest_evidence is not None
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.window.end_date,
        data_quality_status=quality_status,
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=source_refs,
        lineage={
            "source_owner": "lotus-core",
            "source_product": "DataQualityCoverageReport",
            "coverage_kind": coverage_kind,
            identifier_key: identifier_value,
        },
        source_evidence_current=current,
        freshness_status=(
            "CURRENT"
            if current
            else "UNAVAILABLE"
            if not observed_dates
            else "PARTIAL"
        ),
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return CoverageResponse(
        request_fingerprint=fingerprint,
        observed_start_date=min(observed_dates) if observed_dates else None,
        observed_end_date=max(observed_dates) if observed_dates else None,
        expected_start_date=request.window.start_date,
        expected_end_date=request.window.end_date,
        total_points=total_points,
        missing_dates_count=missing_count,
        missing_dates_sample=missing_sample,
        quality_status_distribution=quality_distribution,
        **metadata,
    )


def observed_benchmark_dates(
    *,
    components: list[BenchmarkComponentEvidence],
    prices: list[IndexPriceEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    start_date: date,
    end_date: date,
) -> list[date]:
    """Return dates with a benchmark return and every active component price."""

    price_ids_by_date: dict[date, set[str]] = {}
    for row in prices:
        price_ids_by_date.setdefault(row.series_date, set()).add(row.index_id)
    return_dates = {row.series_date for row in benchmark_returns}
    candidate_dates = sorted(return_dates & set(price_ids_by_date))
    return [
        current_date
        for current_date in candidate_dates
        if (
            active_ids := _active_component_ids(
                components=components,
                current_date=current_date,
                start_date=start_date,
                end_date=end_date,
            )
        )
        and active_ids <= price_ids_by_date[current_date]
    ]


def _active_component_ids(
    *,
    components: list[BenchmarkComponentEvidence],
    current_date: date,
    start_date: date,
    end_date: date,
) -> set[str]:
    return {
        component.index_id
        for component in components
        if max(component.composition_effective_from, start_date)
        <= current_date
        <= min(component.composition_effective_to or end_date, end_date)
    }


def _quality_distribution(rows: Sequence[QualityEvidence]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for row in rows:
        key = quality_status_summary_key(row.quality_status)
        distribution[key] = distribution.get(key, 0) + 1
    return dict(sorted(distribution.items()))


def _coverage_quality_status(
    *, required_count: int, observed_count: int, quality_distribution: dict[str, int]
) -> str:
    normalized = {status.upper(): count for status, count in quality_distribution.items()}
    return cast(
        str,
        classify_market_reference_coverage(
            MarketReferenceCoverageSignal(
                required_count=required_count,
                observed_count=observed_count,
                stale_count=sum(
                    count
                    for status, count in normalized.items()
                    if status in STALE_QUALITY_STATUSES
                ),
                estimated_count=sum(
                    count
                    for status, count in normalized.items()
                    if status in PARTIAL_QUALITY_STATUSES
                ),
                blocking_count=sum(
                    count
                    for status, count in normalized.items()
                    if status in BLOCKING_QUALITY_STATUSES
                ),
            )
        ),
    )


def _missing_dates(
    *, start_date: date, end_date: date, observed_dates: set[date]
) -> tuple[int, list[date]]:
    missing_count = 0
    sample: list[date] = []
    current_date = start_date
    while current_date <= end_date:
        if current_date not in observed_dates:
            missing_count += 1
            if len(sample) < 10:
                sample.append(current_date)
        current_date += timedelta(days=1)
    return missing_count, sample


def _expected_date_count(*, start_date: date, end_date: date) -> int:
    return max(0, (end_date - start_date).days + 1)
