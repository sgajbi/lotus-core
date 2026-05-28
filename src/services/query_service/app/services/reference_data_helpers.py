from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from portfolio_common.market_reference_quality import (
    BLOCKING_QUALITY_STATUSES,
    PARTIAL_QUALITY_STATUSES,
    STALE_QUALITY_STATUSES,
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
)


def latest_reference_evidence_timestamp(*row_groups: list[Any]) -> datetime | None:
    timestamps: list[datetime] = []
    for rows in row_groups:
        for row in rows:
            for field_name in (
                "observed_at",
                "source_timestamp",
                "assignment_recorded_at",
                "updated_at",
                "created_at",
            ):
                value = getattr(row, field_name, None)
                if isinstance(value, datetime):
                    timestamps.append(value)
    return max(timestamps) if timestamps else None


def market_reference_data_quality_status(rows: list[Any], required_count: int) -> str:
    if required_count <= 0:
        return "UNKNOWN"
    quality_statuses = [
        str(status).strip().upper()
        for row in rows
        if (status := getattr(row, "quality_status", None)) is not None
    ]
    if not quality_statuses:
        return "UNKNOWN"
    return classify_market_reference_coverage(
        MarketReferenceCoverageSignal(
            required_count=required_count,
            observed_count=len(quality_statuses),
            stale_count=sum(1 for status in quality_statuses if status in STALE_QUALITY_STATUSES),
            estimated_count=sum(
                1 for status in quality_statuses if status in PARTIAL_QUALITY_STATUSES
            ),
            blocking_count=sum(
                1 for status in quality_statuses if status in BLOCKING_QUALITY_STATUSES
            ),
        )
    )


def latest_effective_records(
    rows: list[Any],
    *,
    key_fields: tuple[str, ...],
    effective_from_field: str,
) -> list[Any]:
    latest_by_key: dict[tuple[Any, ...], Any] = {}
    for row in sorted(
        rows,
        key=lambda item: (
            *[getattr(item, field) for field in key_fields],
            getattr(item, effective_from_field),
        ),
        reverse=True,
    ):
        record_key = tuple(getattr(row, field) for field in key_fields)
        latest_by_key.setdefault(record_key, row)
    return sorted(
        latest_by_key.values(),
        key=lambda item: tuple(getattr(item, field) for field in key_fields),
    )


def resolve_component_window_rows(
    rows: list[Any],
    *,
    start_date: date,
    end_date: date,
) -> list[Any]:
    rows_by_index: dict[str, list[Any]] = {}
    for row in rows:
        rows_by_index.setdefault(row.index_id, []).append(row)

    resolved_rows: list[Any] = []
    for index_id, index_rows in rows_by_index.items():
        sorted_rows = sorted(
            index_rows,
            key=lambda item: item.composition_effective_from,
        )
        for position, row in enumerate(sorted_rows):
            next_start = (
                sorted_rows[position + 1].composition_effective_from
                if position + 1 < len(sorted_rows)
                else None
            )
            resolved_end = row.composition_effective_to
            if next_start is not None:
                inferred_end = next_start - timedelta(days=1)
                if resolved_end is None or resolved_end >= next_start:
                    resolved_end = inferred_end
                else:
                    resolved_end = min(resolved_end, inferred_end)
            if row.composition_effective_from > end_date:
                continue
            if resolved_end is not None and resolved_end < start_date:
                continue
            resolved_rows.append(
                SimpleNamespace(
                    index_id=index_id,
                    composition_weight=row.composition_weight,
                    composition_effective_from=row.composition_effective_from,
                    composition_effective_to=resolved_end,
                    rebalance_event_id=getattr(row, "rebalance_event_id", None),
                    quality_status=getattr(row, "quality_status", None),
                    source_timestamp=getattr(row, "source_timestamp", None),
                    observed_at=getattr(row, "observed_at", None),
                    updated_at=getattr(row, "updated_at", None),
                )
            )
    return sorted(
        resolved_rows,
        key=lambda item: (item.composition_effective_from, item.index_id),
    )
