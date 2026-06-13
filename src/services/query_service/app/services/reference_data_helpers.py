from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from portfolio_common.market_reference_quality import (
    BLOCKING_QUALITY_STATUSES,
    PARTIAL_QUALITY_STATUSES,
    STALE_QUALITY_STATUSES,
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
)

REFERENCE_EVIDENCE_TIMESTAMP_FIELDS = (
    "observed_at",
    "source_timestamp",
    "assignment_recorded_at",
    "updated_at",
    "created_at",
)


def latest_reference_evidence_timestamp(*row_groups: list[Any]) -> datetime | None:
    timestamps = list(_reference_evidence_timestamps(row_groups))
    return max(timestamps) if timestamps else None


def _reference_evidence_timestamps(row_groups: tuple[list[Any], ...]) -> list[datetime]:
    timestamps: list[datetime] = []
    for rows in row_groups:
        for row in rows:
            timestamps.extend(_row_reference_evidence_timestamps(row))
    return timestamps


def _row_reference_evidence_timestamps(row: Any) -> list[datetime]:
    return [
        value
        for field_name in REFERENCE_EVIDENCE_TIMESTAMP_FIELDS
        if isinstance(value := getattr(row, field_name, None), datetime)
    ]


def market_reference_data_quality_status(rows: list[Any], required_count: int) -> str:
    if required_count <= 0:
        return "UNKNOWN"
    quality_statuses = _quality_statuses(rows)
    if not quality_statuses:
        return "UNKNOWN"
    return cast(
        str,
        classify_market_reference_coverage(
            _market_reference_coverage_signal(
                required_count=required_count,
                quality_statuses=quality_statuses,
            )
        ),
    )


def _quality_statuses(rows: list[Any]) -> list[str]:
    return [
        str(status).strip().upper()
        for row in rows
        if (status := getattr(row, "quality_status", None)) is not None
    ]


def _status_count(quality_statuses: list[str], status_family: set[str]) -> int:
    return sum(1 for status in quality_statuses if status in status_family)


def _market_reference_coverage_signal(
    *,
    required_count: int,
    quality_statuses: list[str],
) -> MarketReferenceCoverageSignal:
    return MarketReferenceCoverageSignal(
        required_count=required_count,
        observed_count=len(quality_statuses),
        stale_count=_status_count(quality_statuses, STALE_QUALITY_STATUSES),
        estimated_count=_status_count(quality_statuses, PARTIAL_QUALITY_STATUSES),
        blocking_count=_status_count(quality_statuses, BLOCKING_QUALITY_STATUSES),
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
    resolved_rows: list[Any] = []
    for index_id, index_rows in _component_rows_by_index(rows).items():
        sorted_rows = _sort_component_rows(index_rows)
        for position, row in enumerate(sorted_rows):
            resolved_end = _component_window_end(
                row,
                next_row=_next_component_row(sorted_rows, position),
            )
            if not _component_window_overlaps(
                row,
                resolved_end=resolved_end,
                start_date=start_date,
                end_date=end_date,
            ):
                continue
            resolved_rows.append(_resolved_component_window_row(index_id, row, resolved_end))
    return sorted(
        resolved_rows,
        key=lambda item: (item.composition_effective_from, item.index_id),
    )


def _component_rows_by_index(rows: list[Any]) -> dict[str, list[Any]]:
    rows_by_index: dict[str, list[Any]] = {}
    for row in rows:
        rows_by_index.setdefault(row.index_id, []).append(row)
    return rows_by_index


def _sort_component_rows(rows: list[Any]) -> list[Any]:
    return sorted(
        rows,
        key=lambda item: item.composition_effective_from,
    )


def _next_component_row(sorted_rows: list[Any], position: int) -> Any | None:
    next_position = position + 1
    return sorted_rows[next_position] if next_position < len(sorted_rows) else None


def _component_window_end(row: Any, *, next_row: Any | None) -> date | None:
    resolved_end = cast(date | None, row.composition_effective_to)
    if next_row is None:
        return resolved_end

    next_start = cast(date, next_row.composition_effective_from)
    inferred_end = next_start - timedelta(days=1)
    if resolved_end is None or resolved_end >= next_start:
        return inferred_end
    return min(resolved_end, inferred_end)


def _component_window_overlaps(
    row: Any,
    *,
    resolved_end: date | None,
    start_date: date,
    end_date: date,
) -> bool:
    if row.composition_effective_from > end_date:
        return False
    return resolved_end is None or resolved_end >= start_date


def _resolved_component_window_row(index_id: str, row: Any, resolved_end: date | None) -> Any:
    return SimpleNamespace(
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
