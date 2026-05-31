from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..dtos.reference_integration_dto import TransactionCostCurvePoint
from ..repositories.identifier_normalization import normalize_security_id


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


def has_observed_transaction_cost_evidence(transaction: Any) -> bool:
    fee_amount = transaction_fee_amount(transaction)
    notional = abs(_as_decimal(transaction.gross_transaction_amount))
    return fee_amount > 0 and notional > 0


def build_transaction_cost_curve_point(
    *,
    portfolio_id: str,
    key: tuple[str, str, str],
    rows: list[Any],
) -> TransactionCostCurvePoint | None:
    security_id, transaction_type, currency = key
    total_cost = sum(transaction_fee_amount(row) for row in rows)
    total_notional = sum(abs(_as_decimal(row.gross_transaction_amount)) for row in rows)
    if total_cost <= 0 or total_notional <= 0:
        return None

    cost_bps_values = [
        (transaction_fee_amount(row) / abs(_as_decimal(row.gross_transaction_amount)))
        * Decimal("10000")
        for row in rows
        if abs(_as_decimal(row.gross_transaction_amount)) > 0
    ]
    if not cost_bps_values:
        return None

    observed_dates = [row.transaction_date.date() for row in rows]
    return TransactionCostCurvePoint(
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_type=transaction_type,
        currency=currency,
        observation_count=len(rows),
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
            str(row.transaction_id) for row in sorted(rows, key=lambda row: row.transaction_id)[:5]
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
    grouped: dict[tuple[str, str, str], list[Any]] = {}
    for transaction in transactions:
        if not has_observed_transaction_cost_evidence(transaction):
            continue
        grouped.setdefault(transaction_cost_curve_key(transaction), []).append(transaction)

    points: list[TransactionCostCurvePoint] = []
    for key in sorted(grouped):
        rows = grouped[key]
        if len(rows) < min_observation_count:
            continue
        point = build_transaction_cost_curve_point(
            portfolio_id=portfolio_id,
            key=key,
            rows=rows,
        )
        if point is not None:
            points.append(point)
    return points
