from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from portfolio_common.market_reference_quality import (
    quality_status_summary_key,
)


def latest_reference_evidence_timestamp(rows: list[Any]) -> datetime | None:
    timestamps: list[datetime] = []
    for row in rows:
        for field_name in ("observed_at", "source_timestamp", "updated_at", "created_at"):
            value = getattr(row, field_name, None)
            if isinstance(value, datetime):
                timestamps.append(value)
    return max(timestamps) if timestamps else None


def quality_status_counts(rows: list[Any]) -> dict[str, int]:
    quality_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        quality_counts[quality_status_summary_key(row.quality_status)] += 1
    return dict(quality_counts)


def observed_benchmark_coverage_dates(
    *,
    components: list[Any],
    price_points: list[Any],
    benchmark_returns: list[Any],
    start_date: date,
    end_date: date,
) -> list[date]:
    price_index_ids_by_date = _index_ids_by_series_date(price_points)
    benchmark_return_dates = {row.series_date for row in benchmark_returns}
    candidate_dates = sorted(benchmark_return_dates & set(price_index_ids_by_date))
    return [
        current_date
        for current_date in candidate_dates
        if (
            required_index_ids := _active_component_index_ids(
                components=components,
                current_date=current_date,
                start_date=start_date,
                end_date=end_date,
            )
        )
        and required_index_ids.issubset(price_index_ids_by_date.get(current_date, set()))
    ]


def _index_ids_by_series_date(rows: list[Any]) -> dict[date, set[str]]:
    index_ids_by_date: dict[date, set[str]] = defaultdict(set)
    for row in rows:
        index_ids_by_date[row.series_date].add(row.index_id)
    return index_ids_by_date


def _active_component_index_ids(
    *,
    components: list[Any],
    current_date: date,
    start_date: date,
    end_date: date,
) -> set[str]:
    active_index_ids: set[str] = set()
    for component in components:
        component_start = max(
            getattr(component, "composition_effective_from", start_date),
            start_date,
        )
        component_end = min(
            getattr(component, "composition_effective_to", None) or end_date,
            end_date,
        )
        if component_start <= current_date <= component_end:
            active_index_ids.add(component.index_id)
    return active_index_ids
