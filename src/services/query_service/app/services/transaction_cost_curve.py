from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..dtos.reference_integration_dto import TransactionCostCurvePoint
from ..repositories.identifier_normalization import normalize_security_id


@dataclass(frozen=True)
class _CostObservation:
    row: Any
    fee_amount: Decimal
    notional: Decimal


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def transaction_fee_amount(transaction: Any) -> Decimal:
    costs = list(getattr(transaction, "costs", None) or [])
    if costs:
        return sum((_as_decimal(getattr(cost, "amount", Decimal("0")))) for cost in costs)
    trade_fee = getattr(transaction, "trade_fee", None)
    if trade_fee is None:
        return Decimal("0")
    return _as_decimal(trade_fee)


def transaction_cost_curve_key(transaction: Any) -> tuple[str, str, str]:
    return (
        normalize_security_id(transaction.security_id),
        str(transaction.transaction_type).strip().upper(),
        str(transaction.currency).strip().upper(),
    )


def _cost_observation(transaction: Any) -> _CostObservation | None:
    fee_amount = transaction_fee_amount(transaction)
    notional = abs(_as_decimal(transaction.gross_transaction_amount))
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
    grouped: dict[tuple[str, str, str], list[_CostObservation]] = {}
    for transaction in transactions:
        observation = _cost_observation(transaction)
        if observation is None:
            continue
        grouped.setdefault(transaction_cost_curve_key(transaction), []).append(observation)

    points: list[TransactionCostCurvePoint] = []
    for key in sorted(grouped):
        observations = grouped[key]
        if len(observations) < min_observation_count:
            continue
        point = _build_transaction_cost_curve_point_from_observations(
            portfolio_id=portfolio_id,
            key=key,
            observations=observations,
        )
        if point is not None:
            points.append(point)
    return points
