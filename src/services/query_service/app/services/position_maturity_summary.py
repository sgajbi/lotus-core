from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, STALE, UNKNOWN

from ..dtos.position_dto import (
    PortfolioMaturitySummaryResponse,
    PortfolioPositionsResponse,
    Position,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata

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
MISSING_INSTRUMENT_MATURITY_DATE = "MISSING_INSTRUMENT_MATURITY_DATE"
UNSUPPORTED_PRODUCT_MATURITY_FEATURE = "UNSUPPORTED_PRODUCT_MATURITY_FEATURE"


def portfolio_maturity_summary_response(
    *,
    portfolio_id: str,
    holdings: PortfolioPositionsResponse,
    horizon_days: int,
    include_projected: bool,
) -> PortfolioMaturitySummaryResponse:
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
            reasons=reasons,
        ),
        "supportability_reasons": reasons,
    }
    return PortfolioMaturitySummaryResponse(
        **response_values,
        request_fingerprint=_maturity_summary_fingerprint(
            holdings=holdings,
            response_values=response_values,
        ),
        **source_data_product_runtime_metadata(
            as_of_date=holdings.as_of_date,
            data_quality_status=_summary_data_quality_status(
                holdings_data_quality_status=holdings.data_quality_status,
                reasons=reasons,
            ),
            latest_evidence_timestamp=holdings.latest_evidence_timestamp,
            snapshot_id=holdings.snapshot_id,
            policy_version=holdings.policy_version,
        ),
        freshness_status=_freshness_status(holdings.data_quality_status),
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


def _freshness_status(data_quality_status: str) -> str:
    normalized = _normalized_quality(data_quality_status)
    if normalized == STALE:
        return FRESHNESS_STALE
    if normalized in {COMPLETE, PARTIAL}:
        return FRESHNESS_CURRENT
    return FRESHNESS_UNKNOWN


def _summary_data_quality_status(
    *,
    holdings_data_quality_status: str,
    reasons: list[str],
) -> str:
    normalized = _normalized_quality(holdings_data_quality_status)
    if normalized == STALE:
        return STALE
    if normalized == UNKNOWN:
        return UNKNOWN
    if reasons:
        return PARTIAL
    return COMPLETE


def _supportability_status(*, data_quality_status: str, reasons: list[str]) -> str:
    normalized = _normalized_quality(data_quality_status)
    if normalized == UNKNOWN:
        return UNAVAILABLE
    if normalized == STALE:
        return STALE_SUPPORT
    if reasons:
        return PARTIAL_SUPPORT
    return SUPPORTED


def _supportability_reasons(
    *,
    data_quality_status: str,
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
    if missing_maturity_count:
        reasons.append(MISSING_INSTRUMENT_MATURITY_DATE)
    if unsupported_feature_count:
        reasons.append(UNSUPPORTED_PRODUCT_MATURITY_FEATURE)
    return reasons


def _normalized_quality(data_quality_status: str) -> str:
    return (data_quality_status or UNKNOWN).strip().upper()


def _maturity_summary_fingerprint(
    *,
    holdings: PortfolioPositionsResponse,
    response_values: dict[str, object],
) -> str:
    payload = {
        "product_name": "PortfolioMaturitySummary",
        "product_version": "v1",
        "source_product_name": holdings.product_name,
        "source_product_version": holdings.product_version,
        "as_of_date": holdings.as_of_date.isoformat(),
        "latest_evidence_timestamp": (
            holdings.latest_evidence_timestamp.isoformat()
            if holdings.latest_evidence_timestamp
            else None
        ),
        **{
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in response_values.items()
        },
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"maturity_summary:{digest}"
