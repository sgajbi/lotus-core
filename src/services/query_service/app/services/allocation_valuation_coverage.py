from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.logging_utils import operation_log_extra

from ..domain.strict_decimal import decimal_or_none, decimal_or_zero
from ..dtos.reporting_dto import AllocationValuationCoverage, ReportingScopeType
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.reporting_repository import SnapshotPresence
from .control_code_normalization import normalize_control_code
from .valuation_status import has_usable_valuation_status

logger = logging.getLogger(__name__)
ZERO = Decimal("0")

AllocationReportingValue = tuple[Any, Decimal | None, Decimal | None, str | None]
ResolvedAllocationRow = tuple[Any, str | None, Decimal | None, Decimal | None, str | None]
ConvertAmount = Callable[..., Awaitable[Decimal]]


def allocation_parent_security_ids(rows: list[Any]) -> tuple[list[str], list[str | None]]:
    parent_security_ids: list[str] = []
    row_parent_security_ids: list[str | None] = []
    for row in rows:
        parent_security_id = normalize_security_id(row.snapshot.security_id)
        if parent_security_id:
            parent_security_ids.append(parent_security_id)
        row_parent_security_ids.append(parent_security_id)
    return list(dict.fromkeys(parent_security_ids)), row_parent_security_ids


def resolved_allocation_rows(
    *,
    reporting_values: list[AllocationReportingValue],
    row_parent_security_ids: list[str | None],
) -> list[ResolvedAllocationRow]:
    return [
        (row, parent_security_id, reporting_value, source_value, valuation_status)
        for (row, source_value, reporting_value, valuation_status), parent_security_id in zip(
            reporting_values,
            row_parent_security_ids,
            strict=True,
        )
    ]


def evaluate_allocation_valuation_coverage(
    *,
    rows: list[Any],
    presence_by_portfolio: dict[str, SnapshotPresence],
    portfolio_ids: list[str],
    resolved_as_of_date: date,
) -> AllocationValuationCoverage:
    observed_count = len(rows)
    expected_count = sum(
        presence_by_portfolio[portfolio_id].expected_open_count
        for portfolio_id in portfolio_ids
        if portfolio_id in presence_by_portfolio
    )
    unvalued_count = sum(
        1
        for row in rows
        if row.snapshot.market_value is None
        or not has_usable_valuation_status(row.snapshot.valuation_status)
    )
    valued_count = observed_count - unvalued_count
    missing_presence = any(
        portfolio_id not in presence_by_portfolio for portfolio_id in portfolio_ids
    )

    if not rows:
        if missing_presence:
            state, reason = "UNAVAILABLE", "no_source_snapshot"
        elif expected_count:
            state, reason = "UNAVAILABLE", "open_position_coverage_gap"
        else:
            state, reason = "LOADED_EMPTY", "source_snapshot_has_no_open_positions"
    elif missing_presence:
        state, reason = "PARTIAL", "portfolio_snapshot_missing"
    elif expected_count > observed_count:
        state, reason = "PARTIAL", "open_position_coverage_gap"
    elif any(row.snapshot.market_value is None for row in rows):
        state, reason = "PARTIAL", "market_value_missing"
    elif any(not has_usable_valuation_status(row.snapshot.valuation_status) for row in rows):
        state, reason = "PARTIAL", "valuation_status_not_valued"
    elif any(row.snapshot.date < resolved_as_of_date for row in rows):
        state, reason = "CARRY_FORWARD", "latest_source_snapshot_precedes_as_of_date"
    elif all(decimal_or_zero(row.snapshot.market_value) == ZERO for row in rows):
        state, reason = "MEASURED_ZERO", "source_measured_zero"
    else:
        state, reason = "COMPLETE", "all_source_positions_covered"

    return AllocationValuationCoverage(
        coverage_state=state,
        coverage_reason=reason,
        snapshot_row_count=observed_count,
        expected_open_position_count=expected_count,
        valued_position_count=valued_count,
        unvalued_position_count=unvalued_count,
    )


def log_degraded_allocation_coverage(
    *,
    coverage: AllocationValuationCoverage,
    scope_type: ReportingScopeType,
) -> None:
    logger.warning(
        "Asset allocation valuation coverage is degraded.",
        extra=operation_log_extra(
            event_name="query.reporting.asset_allocation_valuation_degraded",
            operation="query.reporting.get_asset_allocation",
            status="degraded",
            reason_code=coverage.coverage_reason,
            scope_type=scope_type,
            snapshot_row_count=coverage.snapshot_row_count,
            expected_open_position_count=coverage.expected_open_position_count,
            valued_position_count=coverage.valued_position_count,
            unvalued_position_count=coverage.unvalued_position_count,
        ),
    )


async def allocation_reporting_values(
    *,
    rows: list[Any],
    as_of_date: date,
    reporting_currency: str,
    convert_amount: ConvertAmount,
) -> list[AllocationReportingValue]:
    """Convert only source values whose monetary status is usable for allocation."""

    values: list[AllocationReportingValue] = []
    for row in rows:
        source_value = decimal_or_none(row.snapshot.market_value)
        valuation_status = normalize_control_code(row.snapshot.valuation_status) or None
        reporting_value: Decimal | None = None
        if source_value is not None and has_usable_valuation_status(valuation_status):
            reporting_value = await convert_amount(
                amount=source_value,
                from_currency=str(normalize_currency_code(str(row.portfolio.base_currency))),
                to_currency=str(normalize_currency_code(reporting_currency)),
                as_of_date=as_of_date,
            )
        values.append((row, source_value, reporting_value, valuation_status))
    return values


async def resolve_allocation_valuation_coverage(
    *,
    repository: Any,
    rows: list[Any],
    portfolio_ids: list[str],
    resolved_as_of_date: date,
    scope_type: ReportingScopeType,
) -> tuple[AllocationValuationCoverage, bool]:
    raw_presence = await repository.list_snapshot_presence(
        portfolio_ids=portfolio_ids,
        as_of_date=resolved_as_of_date,
    )
    if isinstance(raw_presence, dict):
        snapshot_presence = raw_presence
    else:
        rows_by_portfolio: dict[str, list[Any]] = defaultdict(list)
        for row in rows:
            rows_by_portfolio[str(row.portfolio.portfolio_id)].append(row)
        snapshot_presence = {
            portfolio_id: SnapshotPresence(
                snapshot_date=max(row.snapshot.date for row in portfolio_rows),
                row_count=len(portfolio_rows),
                expected_open_count=len(portfolio_rows),
            )
            for portfolio_id, portfolio_rows in rows_by_portfolio.items()
        }
    coverage = evaluate_allocation_valuation_coverage(
        rows=rows,
        presence_by_portfolio=snapshot_presence,
        portfolio_ids=portfolio_ids,
        resolved_as_of_date=resolved_as_of_date,
    )
    complete = coverage.coverage_state in {
        "COMPLETE",
        "MEASURED_ZERO",
        "CARRY_FORWARD",
        "LOADED_EMPTY",
    }
    if not complete:
        log_degraded_allocation_coverage(coverage=coverage, scope_type=scope_type)
    return coverage, complete
