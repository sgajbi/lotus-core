from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.reconciliation_quality import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    STALE,
    UNKNOWN,
    UNRECONCILED,
    reconciliation_bound_data_quality_status,
)
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..dtos.position_dto import (
    PortfolioMaturitySummaryResponse,
    PortfolioPositionsResponse,
    Position,
)

MATURITY_BEARING_TERMS = (
    "BOND",
    "FIXED INCOME",
    "FIXED-INCOME",
    "DEBT",
    "NOTE",
    "BILL",
    "CERTIFICATE",
    "DEBENTURE",
)
UNSUPPORTED_MATURITY_FEATURE_TERMS = (
    "CALLABLE",
    "PUTABLE",
    "AMORTIZING",
    "STRUCTURED",
    "LOCKUP",
    "LOCK-UP",
    "EXPIRY",
    "EXPIRATION",
)

FRESHNESS_CURRENT = "CURRENT"
FRESHNESS_STALE = "STALE"
FRESHNESS_UNKNOWN = "UNKNOWN"

SUPPORTED = "SUPPORTED"
PARTIAL_SUPPORT = "PARTIAL"
STALE_SUPPORT = "STALE"
UNAVAILABLE = "UNAVAILABLE"

HOLDINGS_STALE = "HOLDINGS_STALE"
HOLDINGS_PARTIAL = "HOLDINGS_PARTIAL"
HOLDINGS_UNKNOWN = "HOLDINGS_UNKNOWN"
RECONCILIATION_BLOCKED = "HOLDINGS_RECONCILIATION_BLOCKED"
RECONCILIATION_PARTIAL = "HOLDINGS_RECONCILIATION_PARTIAL"
RECONCILIATION_STALE = "HOLDINGS_RECONCILIATION_STALE"
RECONCILIATION_UNKNOWN = "HOLDINGS_RECONCILIATION_UNKNOWN"
RECONCILIATION_MISSING = "HOLDINGS_RECONCILIATION_MISSING"
MISSING_INSTRUMENT_MATURITY_DATE = "MISSING_INSTRUMENT_MATURITY_DATE"
UNSUPPORTED_PRODUCT_MATURITY_FEATURE = "UNSUPPORTED_PRODUCT_MATURITY_FEATURE"

MATURITY_SUMMARY_ALGORITHM_ID = "PORTFOLIO_CONTRACTUAL_MATURITY_SUMMARY"
MATURITY_SUMMARY_ALGORITHM_VERSION = 1
MATURITY_SUMMARY_INTERMEDIATE_PRECISION = 1


def portfolio_maturity_summary_response(
    *,
    portfolio_id: str,
    holdings: PortfolioPositionsResponse,
    horizon_days: int,
    include_projected: bool,
    tenant_id: str | None = None,
) -> PortfolioMaturitySummaryResponse:
    if include_projected:
        raise ValueError("PortfolioMaturitySummary requires include_projected=false")
    normalized_tenant_id = tenant_id.strip() if tenant_id and tenant_id.strip() else None
    window_start_date = holdings.as_of_date
    window_end_date = window_start_date + timedelta(days=horizon_days)
    maturing_positions = [
        position
        for position in holdings.positions
        if _position_has_live_quantity(position)
        and position.maturity_date is not None
        and window_start_date <= position.maturity_date <= window_end_date
    ]
    maturity_bearing_positions = [
        position for position in holdings.positions if _is_maturity_bearing(position)
    ]
    missing_maturity_count = sum(
        1 for position in maturity_bearing_positions if position.maturity_date is None
    )
    unsupported_feature_count = sum(
        1 for position in holdings.positions if _has_unsupported_maturity_feature(position)
    )
    reasons = _supportability_reasons(
        data_quality_status=holdings.data_quality_status,
        reconciliation_status=holdings.reconciliation_status,
        missing_maturity_count=missing_maturity_count,
        unsupported_feature_count=unsupported_feature_count,
    )
    next_maturity_date = min(
        (position.maturity_date for position in maturing_positions if position.maturity_date),
        default=None,
    )
    response_values = {
        "portfolio_id": portfolio_id,
        "include_projected": include_projected,
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
        "horizon_days": horizon_days,
        "next_maturity_date": next_maturity_date,
        "maturing_holding_count": len(maturing_positions),
        "maturity_bearing_holding_count": len(maturity_bearing_positions),
        "missing_maturity_date_count": missing_maturity_count,
        "unsupported_maturity_feature_count": unsupported_feature_count,
        "supportability_status": _supportability_status(
            data_quality_status=holdings.data_quality_status,
            reconciliation_status=holdings.reconciliation_status,
            reasons=reasons,
        ),
        "supportability_reasons": reasons,
    }
    calculation_lineage = build_calculation_lineage(
        algorithm_id=MATURITY_SUMMARY_ALGORITHM_ID,
        algorithm_version=MATURITY_SUMMARY_ALGORITHM_VERSION,
        intermediate_precision=MATURITY_SUMMARY_INTERMEDIATE_PRECISION,
        input_payload={
            "portfolio_id": portfolio_id,
            "tenant_id": normalized_tenant_id,
            "horizon_days": horizon_days,
            "include_projected": False,
            "source_product_name": holdings.product_name,
            "source_product_version": holdings.product_version,
            "holdings_as_of_date": holdings.as_of_date,
            "holdings_snapshot_id": holdings.snapshot_id,
            "holdings_content_hash": holdings.content_hash,
            "holdings_source_batch_fingerprint": holdings.source_batch_fingerprint,
            "holdings_policy_version": holdings.policy_version,
            "holdings_latest_evidence_timestamp": holdings.latest_evidence_timestamp,
            "holdings_reconciliation_status": holdings.reconciliation_status,
        },
        output_payload=response_values,
    )
    request_fingerprint = f"maturity_summary:{calculation_lineage.input_content_hash[:16]}"
    content_hash = stable_content_hash(
        {
            "product_name": "PortfolioMaturitySummary",
            "product_version": "v1",
            "source_product_name": holdings.product_name,
            "source_product_version": holdings.product_version,
            "portfolio_id": portfolio_id,
            "tenant_id": normalized_tenant_id,
            "request_fingerprint": request_fingerprint,
            "response_values": response_values,
            "calculation_lineage": calculation_lineage.lineage_payload(),
            "holdings_content_hash": holdings.content_hash,
            "holdings_snapshot_id": holdings.snapshot_id,
            "latest_evidence_timestamp": holdings.latest_evidence_timestamp,
        }
    )
    return PortfolioMaturitySummaryResponse(
        **response_values,
        request_fingerprint=request_fingerprint,
        calculation_lineage=calculation_lineage.lineage_payload(),
        **source_data_product_runtime_metadata(
            as_of_date=holdings.as_of_date,
            tenant_id=normalized_tenant_id,
            reconciliation_status=holdings.reconciliation_status,
            data_quality_status=_summary_data_quality_status(
                holdings_data_quality_status=holdings.data_quality_status,
                reconciliation_status=holdings.reconciliation_status,
                reasons=reasons,
            ),
            latest_evidence_timestamp=holdings.latest_evidence_timestamp,
            snapshot_id=holdings.snapshot_id,
            policy_version=holdings.policy_version,
            content_hash=content_hash,
            freshness_status=_freshness_status(
                data_quality_status=holdings.data_quality_status,
                reconciliation_status=holdings.reconciliation_status,
            ),
            source_refs=[
                "lotus-core://source/PortfolioMaturitySummary/"
                f"{portfolio_id}/{window_start_date.isoformat()}/{window_end_date.isoformat()}"
            ],
            lineage={
                "source_owner": "lotus-core",
                "source_product": "PortfolioMaturitySummary",
                "upstream_product": holdings.product_name,
                "upstream_content_hash": holdings.content_hash,
                "input_content_hash": calculation_lineage.input_content_hash,
                "calculation_content_hash": calculation_lineage.calculation_content_hash,
                "output_content_hash": calculation_lineage.output_content_hash,
                "algorithm_id": calculation_lineage.algorithm_id,
                "algorithm_version": str(calculation_lineage.algorithm_version),
            },
            source_evidence_current=(
                holdings.reconciliation_status == COMPLETE
                and _freshness_status(
                    data_quality_status=holdings.data_quality_status,
                    reconciliation_status=holdings.reconciliation_status,
                )
                == FRESHNESS_CURRENT
            ),
            use_content_hash_as_source_batch_fingerprint=True,
        ),
    )


def _is_maturity_bearing(position: Position) -> bool:
    return _field_contains_any(
        (position.asset_class, position.product_type),
        MATURITY_BEARING_TERMS,
    )


def _has_unsupported_maturity_feature(position: Position) -> bool:
    return _field_contains_any(
        (position.asset_class, position.product_type, position.instrument_name),
        UNSUPPORTED_MATURITY_FEATURE_TERMS,
    )


def _field_contains_any(values: tuple[str | None, ...], terms: tuple[str, ...]) -> bool:
    normalized_values = " ".join(value.upper() for value in values if value)
    return any(term in normalized_values for term in terms)


def _position_has_live_quantity(position: Position) -> bool:
    try:
        return Decimal(str(position.quantity)) != Decimal("0")
    except (InvalidOperation, ValueError):
        return False


def _freshness_status(*, data_quality_status: str, reconciliation_status: str) -> str:
    normalized = _normalized_quality(data_quality_status)
    normalized_reconciliation = _normalized_quality(reconciliation_status)
    if normalized == STALE or normalized_reconciliation == STALE:
        return FRESHNESS_STALE
    if normalized in {COMPLETE, PARTIAL} and normalized_reconciliation == COMPLETE:
        return FRESHNESS_CURRENT
    return FRESHNESS_UNKNOWN


def _summary_data_quality_status(
    *,
    holdings_data_quality_status: str,
    reconciliation_status: str,
    reasons: list[str],
) -> str:
    resolved_status = reconciliation_bound_data_quality_status(
        source_data_quality_status=holdings_data_quality_status,
        reconciliation_status=reconciliation_status,
    )
    if resolved_status == COMPLETE and reasons:
        return PARTIAL
    return resolved_status


def _supportability_status(
    *, data_quality_status: str, reconciliation_status: str, reasons: list[str]
) -> str:
    normalized = _normalized_quality(data_quality_status)
    normalized_reconciliation = _normalized_quality(reconciliation_status)
    if normalized == UNKNOWN or normalized_reconciliation in {UNKNOWN, UNRECONCILED, BLOCKED}:
        return UNAVAILABLE
    if normalized == STALE or normalized_reconciliation == STALE:
        return STALE_SUPPORT
    if reasons:
        return PARTIAL_SUPPORT
    return SUPPORTED


def _supportability_reasons(
    *,
    data_quality_status: str,
    reconciliation_status: str,
    missing_maturity_count: int,
    unsupported_feature_count: int,
) -> list[str]:
    reasons: list[str] = []
    normalized = _normalized_quality(data_quality_status)
    if normalized == UNKNOWN:
        reasons.append(HOLDINGS_UNKNOWN)
    elif normalized == STALE:
        reasons.append(HOLDINGS_STALE)
    elif normalized == PARTIAL:
        reasons.append(HOLDINGS_PARTIAL)
    normalized_reconciliation = _normalized_quality(reconciliation_status)
    reconciliation_reason = {
        BLOCKED: RECONCILIATION_BLOCKED,
        PARTIAL: RECONCILIATION_PARTIAL,
        STALE: RECONCILIATION_STALE,
        UNKNOWN: RECONCILIATION_UNKNOWN,
        UNRECONCILED: RECONCILIATION_MISSING,
    }.get(normalized_reconciliation)
    if reconciliation_reason:
        reasons.append(reconciliation_reason)
    if missing_maturity_count:
        reasons.append(MISSING_INSTRUMENT_MATURITY_DATE)
    if unsupported_feature_count:
        reasons.append(UNSUPPORTED_PRODUCT_MATURITY_FEATURE)
    return reasons


def _normalized_quality(data_quality_status: str) -> str:
    return (data_quality_status or UNKNOWN).strip().upper()
