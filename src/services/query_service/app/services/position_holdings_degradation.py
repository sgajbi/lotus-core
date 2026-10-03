from collections.abc import Collection
from datetime import date, datetime
from typing import Any

from portfolio_common.source_data_product_metadata import (
    SourceDataDegradationDetail,
    SourceDataDegradationSummary,
)

from ..application.holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationScopes,
    holdings_reconciliation_status,
)
from ..dtos.position_dto import Position
from ..repositories.identifier_normalization import normalize_security_id
from .position_holdings import PositionRowResult, position_requires_market_price_freshness

VALUATION_FIELDS = [
    "valuation.market_price",
    "valuation.market_value",
    "valuation.unrealized_gain_loss",
    "valuation.market_value_local",
    "valuation.unrealized_gain_loss_local",
]

FX_VALUATION_FIELDS = [
    "valuation.market_value",
    "valuation.unrealized_gain_loss",
    "valuation.unrealized_price_gain_loss",
    "valuation.unrealized_fx_gain_loss",
]


def holdings_degradation_summary(
    *,
    positions: list[Position],
    history_supplements: list[PositionRowResult],
    fallback_valuation_map: dict[str, dict[str, Any] | None],
    response_as_of_date: date,
    latest_market_price_dates: dict[str, date],
    valuation_fx_rate_dates: dict[str, date | None],
    missing_currency_lineage_security_ids: Collection[str],
    latest_evidence_timestamp: datetime | None,
    reconciliation_scopes: HoldingsReconciliationScopes | None = None,
    reconciliation_controls: list[FinancialReconciliationControl] | None = None,
) -> SourceDataDegradationSummary:
    details = (
        _reconciliation_degradation_details(
            scopes=reconciliation_scopes, controls=reconciliation_controls or []
        )
        if reconciliation_scopes is not None
        else []
    )
    if not positions:
        details.append(
            _holdings_degradation_detail(
                section="positions",
                record_key=None,
                affected_fields=["positions"],
                source_kind="UNAVAILABLE",
                source_as_of_date=response_as_of_date,
                latest_evidence_timestamp=latest_evidence_timestamp,
                freshness_status="UNAVAILABLE",
                reason_code="HOLDINGS_EMPTY",
            )
        )
        return _degradation_summary(details)

    history_supplement_ids = {
        security_id
        for position_row, _instrument, _state in history_supplements
        if (security_id := normalize_security_id(position_row.security_id))
    }
    for position in positions:
        security_id = normalize_security_id(position.security_id)
        if not security_id:
            continue
        details.extend(
            _position_state_degradation_details(
                position=position,
                response_as_of_date=response_as_of_date,
                latest_evidence_timestamp=latest_evidence_timestamp,
            )
        )
        details.extend(
            _market_price_degradation_details(
                position=position,
                response_as_of_date=response_as_of_date,
                latest_market_price_dates=latest_market_price_dates,
                latest_evidence_timestamp=latest_evidence_timestamp,
            )
        )
        details.extend(
            _valuation_currency_lineage_degradation_details(
                security_id=security_id,
                missing_currency_lineage_security_ids=(missing_currency_lineage_security_ids),
                latest_evidence_timestamp=latest_evidence_timestamp,
            )
        )
        details.extend(
            _valuation_fx_degradation_details(
                security_id=security_id,
                response_as_of_date=response_as_of_date,
                valuation_fx_rate_dates=valuation_fx_rate_dates,
                latest_evidence_timestamp=latest_evidence_timestamp,
            )
        )
        if security_id in history_supplement_ids:
            details.append(
                _history_supplement_degradation_detail(
                    security_id=security_id,
                    response_as_of_date=response_as_of_date,
                    latest_evidence_timestamp=latest_evidence_timestamp,
                    fallback_valuation=fallback_valuation_map.get(security_id),
                )
            )
    return _degradation_summary(details)


def _reconciliation_degradation_details(
    *,
    scopes: HoldingsReconciliationScopes,
    controls: list[FinancialReconciliationControl],
) -> list[SourceDataDegradationDetail]:
    """Explain exact control qualification using the same policy as the top-level status."""
    details: list[SourceDataDegradationDetail] = []
    for scope in scopes.items:
        status = holdings_reconciliation_status(
            scopes=HoldingsReconciliationScopes(items=(scope,)), controls=controls
        )
        if status == "COMPLETE":
            continue
        details.append(
            _reconciliation_degradation_detail(
                status=status,
                business_date=scope.business_date,
                epoch=scope.epoch,
                evidence_timestamp=scope.latest_evidence_timestamp,
            )
        )
    if scopes.unscoped_source_row_count:
        details.append(
            _reconciliation_degradation_detail(
                status="UNKNOWN", business_date=None, epoch=None, evidence_timestamp=None
            )
        )
    return details


def _reconciliation_degradation_detail(
    *,
    status: str,
    business_date: date | None,
    epoch: int | None,
    evidence_timestamp: datetime | None,
) -> SourceDataDegradationDetail:
    reasons = {
        "STALE": "HOLDINGS_RECONCILIATION_EVIDENCE_NEWER_THAN_CONTROL",
        "UNRECONCILED": "HOLDINGS_RECONCILIATION_CONTROL_MISSING",
        "PARTIAL": "HOLDINGS_RECONCILIATION_INCOMPLETE",
        "BLOCKED": "HOLDINGS_RECONCILIATION_BLOCKED",
        "UNKNOWN": "HOLDINGS_RECONCILIATION_UNKNOWN",
    }
    return _holdings_degradation_detail(
        section="reconciliation",
        record_key=(
            f"business_date:{business_date.isoformat()}:epoch:{epoch}"
            if business_date is not None
            else None
        ),
        affected_fields=["reconciliation_status", "source_evidence_current"],
        source_kind="UNAVAILABLE" if status in {"UNRECONCILED", "UNKNOWN"} else "AUTHORITATIVE",
        source_as_of_date=business_date,
        latest_evidence_timestamp=evidence_timestamp,
        freshness_status=(
            "STALE" if status == "STALE" else "UNKNOWN" if status == "UNKNOWN" else "UNAVAILABLE"
        ),
        reason_code=reasons[status],
    )


def _position_state_degradation_details(
    *,
    position: Position,
    response_as_of_date: date,
    latest_evidence_timestamp: datetime | None,
) -> list[SourceDataDegradationDetail]:
    status = (position.reprocessing_status or "").strip().upper()
    if status == "CURRENT":
        return []
    return [
        _holdings_degradation_detail(
            section="positions",
            record_key=_position_record_key(position.security_id),
            affected_fields=["reprocessing_status"],
            source_kind="AUTHORITATIVE" if status else "UNAVAILABLE",
            source_as_of_date=response_as_of_date,
            latest_evidence_timestamp=latest_evidence_timestamp,
            freshness_status="STALE" if status else "UNKNOWN",
            reason_code=(
                "POSITION_STATE_NOT_CURRENT" if status else "POSITION_STATE_STATUS_MISSING"
            ),
        )
    ]


def _market_price_degradation_details(
    *,
    position: Position,
    response_as_of_date: date,
    latest_market_price_dates: dict[str, date],
    latest_evidence_timestamp: datetime | None,
) -> list[SourceDataDegradationDetail]:
    if not position_requires_market_price_freshness(position):
        return []
    security_id = normalize_security_id(position.security_id)
    latest_price_date = latest_market_price_dates.get(security_id)
    if latest_price_date == response_as_of_date:
        return []
    return [
        _holdings_degradation_detail(
            section="positions",
            record_key=_position_record_key(security_id),
            affected_fields=["valuation.market_price", "valuation.market_value"],
            source_kind="AUTHORITATIVE" if latest_price_date else "UNAVAILABLE",
            source_as_of_date=latest_price_date,
            latest_evidence_timestamp=latest_evidence_timestamp,
            freshness_status="STALE" if latest_price_date else "UNAVAILABLE",
            reason_code=(
                "MARKET_PRICE_STALE" if latest_price_date else "MARKET_PRICE_EVIDENCE_MISSING"
            ),
        )
    ]


def _history_supplement_degradation_detail(
    *,
    security_id: str,
    response_as_of_date: date,
    latest_evidence_timestamp: datetime | None,
    fallback_valuation: dict[str, Any] | None,
) -> SourceDataDegradationDetail:
    if fallback_valuation is None:
        return _holdings_degradation_detail(
            section="positions",
            record_key=_position_record_key(security_id),
            affected_fields=VALUATION_FIELDS,
            source_kind="DERIVED_DEFAULT",
            source_as_of_date=response_as_of_date,
            latest_evidence_timestamp=latest_evidence_timestamp,
            freshness_status="UNAVAILABLE",
            reason_code="SNAPSHOT_VALUATION_FALLBACK_UNAVAILABLE",
        )
    return _holdings_degradation_detail(
        section="positions",
        record_key=_position_record_key(security_id),
        affected_fields=VALUATION_FIELDS,
        source_kind="FALLBACK",
        source_as_of_date=response_as_of_date,
        latest_evidence_timestamp=latest_evidence_timestamp,
        freshness_status="PARTIAL",
        reason_code="HOLDINGS_VALUATION_FALLBACK",
    )


def _valuation_currency_lineage_degradation_details(
    *,
    security_id: str,
    missing_currency_lineage_security_ids: Collection[str],
    latest_evidence_timestamp: datetime | None,
) -> list[SourceDataDegradationDetail]:
    if security_id not in missing_currency_lineage_security_ids:
        return []
    return [
        _holdings_degradation_detail(
            section="positions",
            record_key=_position_record_key(security_id),
            affected_fields=FX_VALUATION_FIELDS,
            source_kind="UNAVAILABLE",
            source_as_of_date=None,
            latest_evidence_timestamp=latest_evidence_timestamp,
            freshness_status="UNKNOWN",
            reason_code="VALUATION_CURRENCY_LINEAGE_MISSING",
        )
    ]


def _valuation_fx_degradation_details(
    *,
    security_id: str,
    response_as_of_date: date,
    valuation_fx_rate_dates: dict[str, date | None],
    latest_evidence_timestamp: datetime | None,
) -> list[SourceDataDegradationDetail]:
    if security_id not in valuation_fx_rate_dates:
        return []
    fx_rate_date = valuation_fx_rate_dates[security_id]
    if fx_rate_date == response_as_of_date:
        return []
    return [
        _holdings_degradation_detail(
            section="positions",
            record_key=_position_record_key(security_id),
            affected_fields=FX_VALUATION_FIELDS,
            source_kind="AUTHORITATIVE" if fx_rate_date else "UNAVAILABLE",
            source_as_of_date=fx_rate_date,
            latest_evidence_timestamp=latest_evidence_timestamp,
            freshness_status="STALE" if fx_rate_date else "UNAVAILABLE",
            reason_code=("FX_RATE_STALE" if fx_rate_date else "FX_RATE_EVIDENCE_MISSING"),
        )
    ]


def _holdings_degradation_detail(
    *,
    section: str,
    record_key: str | None,
    affected_fields: list[str],
    source_kind: str,
    source_as_of_date: date | None,
    latest_evidence_timestamp: datetime | None,
    freshness_status: str,
    reason_code: str,
) -> SourceDataDegradationDetail:
    return SourceDataDegradationDetail(
        section=section,
        record_key=record_key,
        affected_fields=affected_fields,
        source_kind=source_kind,
        source_product_name="HoldingsAsOf",
        source_product_version="v1",
        source_as_of_date=source_as_of_date,
        latest_evidence_timestamp=latest_evidence_timestamp,
        freshness_status=freshness_status,
        reason_code=reason_code,
    )


def _position_record_key(security_id: str) -> str:
    return f"security_id:{normalize_security_id(security_id)}"


def _degradation_summary(
    details: list[SourceDataDegradationDetail],
) -> SourceDataDegradationSummary:
    if not details:
        return SourceDataDegradationSummary()
    return SourceDataDegradationSummary(
        status=_degradation_status(details),
        reason_codes=sorted({detail.reason_code for detail in details}),
        details=details,
    )


def _degradation_status(details: list[SourceDataDegradationDetail]) -> str:
    statuses = {detail.freshness_status for detail in details}
    if "UNAVAILABLE" in statuses:
        return "UNAVAILABLE"
    if "STALE" in statuses:
        return "STALE"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    if "PARTIAL" in statuses:
        return "PARTIAL"
    return "NONE"
