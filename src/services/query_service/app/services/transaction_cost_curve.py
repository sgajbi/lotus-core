from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..dtos.reference_integration_dto import (
    ReferencePageMetadata,
    TransactionCostCurvePoint,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
    TransactionCostCurveSupportability,
)
from ..repositories.identifier_normalization import normalize_security_id
from .decimal_amounts import decimal_or_zero
from .reference_data_helpers import latest_reference_evidence_timestamp
from .request_fingerprint import request_fingerprint as build_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


@dataclass(frozen=True)
class _CostObservation:
    row: Any
    fee_amount: Decimal
    notional: Decimal


@dataclass(frozen=True)
class TransactionCostCurvePage:
    points: list[TransactionCostCurvePoint]
    all_curve_keys: list[tuple[str, str, str]]
    has_more: bool


@dataclass(frozen=True)
class TransactionCostCurveRequestScope:
    request_fingerprint: str
    after_key: tuple[str, str, str] | tuple[()]


def transaction_cost_curve_request_scope(
    *,
    portfolio_id: str,
    request: TransactionCostCurveRequest,
    cursor: dict[str, Any],
) -> TransactionCostCurveRequestScope:
    request_fingerprint = build_request_fingerprint(
        {
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date.isoformat(),
            "window": {
                "start_date": request.window.start_date.isoformat(),
                "end_date": request.window.end_date.isoformat(),
            },
            "security_ids": sorted(request.security_ids or []),
            "transaction_types": sorted(request.transaction_types or []),
            "min_observation_count": request.min_observation_count,
            "tenant_id": request.tenant_id,
        }
    )
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != request_fingerprint:
        raise ValueError("Transaction cost curve page token does not match request scope.")

    return TransactionCostCurveRequestScope(
        request_fingerprint=request_fingerprint,
        after_key=tuple(cursor.get("last_curve_key") or ()),
    )


def transaction_cost_curve_next_page_token_payload(
    *,
    request_scope: TransactionCostCurveRequestScope,
    curve_page: TransactionCostCurvePage,
) -> dict[str, Any] | None:
    if not curve_page.has_more or not curve_page.points:
        return None
    last_point = curve_page.points[-1]
    return {
        "scope_fingerprint": request_scope.request_fingerprint,
        "last_curve_key": [
            last_point.security_id,
            last_point.transaction_type,
            last_point.currency,
        ],
    }


def transaction_fee_amount(transaction: Any) -> Decimal:
    costs = list(getattr(transaction, "costs", None) or [])
    if costs:
        return sum((decimal_or_zero(getattr(cost, "amount", Decimal("0"))) for cost in costs))
    trade_fee = getattr(transaction, "trade_fee", None)
    if trade_fee is None:
        return Decimal("0")
    return decimal_or_zero(trade_fee)


def transaction_cost_curve_key(transaction: Any) -> tuple[str, str, str]:
    return (
        normalize_security_id(transaction.security_id),
        str(transaction.transaction_type).strip().upper(),
        str(transaction.currency).strip().upper(),
    )


def _cost_observation(transaction: Any) -> _CostObservation | None:
    fee_amount = transaction_fee_amount(transaction)
    notional = abs(decimal_or_zero(transaction.gross_transaction_amount))
    if fee_amount <= 0 or notional <= 0:
        return None
    return _CostObservation(row=transaction, fee_amount=fee_amount, notional=notional)


def has_observed_transaction_cost_evidence(transaction: Any) -> bool:
    return _cost_observation(transaction) is not None


def build_transaction_cost_curve_point(
    *,
    portfolio_id: str,
    key: tuple[str, str, str],
    rows: list[Any],
) -> TransactionCostCurvePoint | None:
    observations = [
        observation for row in rows if (observation := _cost_observation(row)) is not None
    ]
    return _build_transaction_cost_curve_point_from_observations(
        portfolio_id=portfolio_id,
        key=key,
        observations=observations,
    )


def _build_transaction_cost_curve_point_from_observations(
    *,
    portfolio_id: str,
    key: tuple[str, str, str],
    observations: list[_CostObservation],
) -> TransactionCostCurvePoint | None:
    security_id, transaction_type, currency = key
    if not observations:
        return None

    total_cost = sum(observation.fee_amount for observation in observations)
    total_notional = sum(observation.notional for observation in observations)
    if total_cost <= 0 or total_notional <= 0:
        return None

    cost_bps_values = [
        (observation.fee_amount / observation.notional) * Decimal("10000")
        for observation in observations
    ]

    observed_dates = [observation.row.transaction_date.date() for observation in observations]
    return TransactionCostCurvePoint(
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_type=transaction_type,
        currency=currency,
        observation_count=len(observations),
        total_notional=total_notional,
        total_cost=total_cost,
        average_cost_bps=(total_cost / total_notional * Decimal("10000")).quantize(
            Decimal("0.0001")
        ),
        min_cost_bps=min(cost_bps_values).quantize(Decimal("0.0001")),
        max_cost_bps=max(cost_bps_values).quantize(Decimal("0.0001")),
        first_observed_date=min(observed_dates),
        last_observed_date=max(observed_dates),
        sample_transaction_ids=[
            str(observation.row.transaction_id)
            for observation in sorted(
                observations, key=lambda observation: observation.row.transaction_id
            )[:5]
        ],
        source_lineage={
            "source_system": "transactions",
            "source_table": "transactions,transaction_costs",
            "contract_version": "rfc_040_wtbd_007_v1",
        },
    )


def build_transaction_cost_curve_points(
    *,
    portfolio_id: str,
    transactions: list[Any],
    min_observation_count: int,
) -> list[TransactionCostCurvePoint]:
    grouped = _group_transaction_cost_observations(transactions)

    points: list[TransactionCostCurvePoint] = []
    for key in _eligible_curve_keys(
        grouped=grouped,
        min_observation_count=min_observation_count,
    ):
        point = _build_transaction_cost_curve_point_from_observations(
            portfolio_id=portfolio_id,
            key=key,
            observations=grouped[key],
        )
        if point is not None:
            points.append(point)
    return points


def build_transaction_cost_curve_page(
    *,
    portfolio_id: str,
    transactions: list[Any],
    min_observation_count: int,
    after_key: tuple[str, str, str] | tuple[()] = (),
    page_size: int,
) -> TransactionCostCurvePage:
    grouped = _group_transaction_cost_observations(transactions)
    all_curve_keys = _eligible_curve_keys(
        grouped=grouped,
        min_observation_count=min_observation_count,
    )
    paged_keys = [key for key in all_curve_keys if not after_key or key > after_key]
    has_more = len(paged_keys) > page_size
    page_keys = paged_keys[:page_size]

    points: list[TransactionCostCurvePoint] = []
    for key in page_keys:
        point = _build_transaction_cost_curve_point_from_observations(
            portfolio_id=portfolio_id,
            key=key,
            observations=grouped[key],
        )
        if point is not None:
            points.append(point)

    return TransactionCostCurvePage(
        points=points,
        all_curve_keys=all_curve_keys,
        has_more=has_more,
    )


def build_transaction_cost_curve_response(
    *,
    portfolio_id: str,
    request: TransactionCostCurveRequest,
    request_scope_fingerprint: str,
    curve_page: TransactionCostCurvePage,
    transactions: list[Any],
    next_page_token: str | None,
) -> TransactionCostCurveResponse:
    requested_security_ids = {
        normalize_security_id(security_id) for security_id in request.security_ids or []
    }
    returned_security_ids = {key[0] for key in curve_page.all_curve_keys}
    missing_security_ids = sorted(requested_security_ids - returned_security_ids)

    supportability_state = "READY"
    supportability_reason = "TRANSACTION_COST_CURVE_READY"
    if not curve_page.all_curve_keys:
        supportability_state = "UNAVAILABLE"
        supportability_reason = "TRANSACTION_COST_EVIDENCE_NOT_FOUND"
    elif missing_security_ids:
        supportability_state = "INCOMPLETE"
        supportability_reason = "TRANSACTION_COST_EVIDENCE_MISSING_FOR_SECURITIES"
    elif curve_page.has_more:
        supportability_state = "DEGRADED"
        supportability_reason = "TRANSACTION_COST_CURVE_PAGE_PARTIAL"

    return TransactionCostCurveResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        window=request.window,
        curve_points=curve_page.points,
        page=ReferencePageMetadata(
            page_size=request.page.page_size,
            sort_key="security_id:asc,transaction_type:asc,currency:asc",
            returned_component_count=len(curve_page.points),
            request_scope_fingerprint=request_scope_fingerprint,
            next_page_token=next_page_token,
        ),
        supportability=TransactionCostCurveSupportability(
            state=supportability_state,
            reason=supportability_reason,
            requested_security_count=(
                len(request.security_ids) if request.security_ids is not None else None
            ),
            returned_curve_point_count=len(curve_page.points),
            missing_security_ids=missing_security_ids,
        ),
        lineage={
            "source_system": "transactions",
            "contract_version": "rfc_040_wtbd_007_v1",
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status="COMPLETE" if supportability_state == "READY" else "PARTIAL",
            latest_evidence_timestamp=latest_reference_evidence_timestamp(transactions),
        ),
    )


def _group_transaction_cost_observations(
    transactions: list[Any],
) -> dict[tuple[str, str, str], list[_CostObservation]]:
    grouped: dict[tuple[str, str, str], list[_CostObservation]] = {}
    for transaction in transactions:
        observation = _cost_observation(transaction)
        if observation is None:
            continue
        grouped.setdefault(transaction_cost_curve_key(transaction), []).append(observation)
    return grouped


def _eligible_curve_keys(
    *,
    grouped: dict[tuple[str, str, str], list[_CostObservation]],
    min_observation_count: int,
) -> list[tuple[str, str, str]]:
    return [key for key in sorted(grouped) if len(grouped[key]) >= min_observation_count]
