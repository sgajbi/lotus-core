"""Fail-closed reconciliation policy shared by cashflow source-data products."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping

from portfolio_common.reconciliation_quality import BLOCKED, COMPLETE

from ..dtos.cashflow_trust_dto import CashflowWindowTrustResponse

EMPTY_SOURCE_WINDOW = "EMPTY_SOURCE_WINDOW"
SOURCE_COUNT_MISMATCH = "SOURCE_COUNT_MISMATCH"
SOURCE_TOTAL_MISMATCH = "SOURCE_TOTAL_MISMATCH"
SOURCE_EVIDENCE_TIMESTAMP_MISSING = "SOURCE_EVIDENCE_TIMESTAMP_MISSING"


@dataclass(frozen=True, slots=True)
class CashflowProductTrust:
    response: CashflowWindowTrustResponse
    reconciliation_status: str
    data_quality_status: str
    source_evidence_current: bool
    freshness_status: str


def reconcile_cashflow_window(
    *,
    source_row_count: int,
    calculated_source_row_count: int,
    output_group_count: int,
    source_component_totals: Mapping[str, Decimal],
    calculated_component_totals: Mapping[str, Decimal],
    latest_evidence_timestamp: datetime | None,
) -> CashflowProductTrust:
    """Compare source controls with calculation results without inventing empty evidence."""

    reasons: list[str] = []
    if source_row_count != calculated_source_row_count:
        reasons.append(SOURCE_COUNT_MISMATCH)
    normalized_source_totals = _normalized_totals(source_component_totals)
    normalized_calculated_totals = _normalized_totals(calculated_component_totals)
    impossible_empty_total = source_row_count == 0 and any(
        total != Decimal("0")
        for total in (*normalized_source_totals.values(), *normalized_calculated_totals.values())
    )
    if normalized_source_totals != normalized_calculated_totals or impossible_empty_total:
        reasons.append(SOURCE_TOTAL_MISMATCH)
    if source_row_count > 0 and latest_evidence_timestamp is None:
        reasons.append(SOURCE_EVIDENCE_TIMESTAMP_MISSING)

    degraded = bool(reasons)
    empty_window = source_row_count == 0 and not degraded
    if empty_window:
        reasons.append(EMPTY_SOURCE_WINDOW)

    response = CashflowWindowTrustResponse(
        window_status="DEGRADED" if degraded else "EMPTY" if empty_window else "POPULATED",
        supportability_status="UNAVAILABLE" if degraded else "SUPPORTED",
        reason_codes=reasons,
        source_row_count=source_row_count,
        calculated_source_row_count=calculated_source_row_count,
        output_group_count=output_group_count,
        source_component_totals=normalized_source_totals,
        calculated_component_totals=normalized_calculated_totals,
    )
    return CashflowProductTrust(
        response=response,
        reconciliation_status=BLOCKED if degraded else COMPLETE,
        data_quality_status=BLOCKED if degraded else COMPLETE,
        source_evidence_current=not degraded,
        freshness_status="UNAVAILABLE" if degraded else "CURRENT",
    )


def _normalized_totals(values: Mapping[str, Decimal]) -> dict[str, Decimal]:
    return {str(key): Decimal(str(value)) for key, value in sorted(values.items())}
