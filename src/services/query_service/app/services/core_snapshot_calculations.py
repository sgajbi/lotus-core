from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..dtos.core_snapshot_dto import CoreSnapshotDeltaRecord, CoreSnapshotPositionRecord
from .decimal_amounts import decimal_or_none, decimal_or_zero


@dataclass(frozen=True)
class DeltaPositionValues:
    quantity: Decimal
    market_value_base: Decimal
    weight: Decimal


def total_market_value_baseline(items: dict[str, dict[str, Any]]) -> Decimal:
    total = Decimal(0)
    for item in items.values():
        market_value = decimal_or_none(item.get("market_value_base"))
        if market_value is not None:
            total += market_value
    return total


def total_market_value_projected(items: dict[str, dict[str, Any]]) -> Decimal:
    total = Decimal(0)
    for item in items.values():
        total += decimal_or_zero(item.get("market_value_base"))
    return total


def assign_baseline_weights(items: dict[str, dict[str, Any]], total: Decimal) -> None:
    for item in items.values():
        if total > 0 and item["market_value_base"] is not None:
            weight = item["market_value_base"] / total
        else:
            weight = Decimal(0)
        item["position_record"] = _position_record(item=item, weight=weight)


def assign_projected_weights(items: dict[str, dict[str, Any]], total: Decimal) -> None:
    for item in items.values():
        weight = (item["market_value_base"] / total) if total > 0 else Decimal(0)
        item["position_record"] = _position_record(item=item, weight=weight)


def build_delta_section(
    baseline_positions: dict[str, dict[str, Any]],
    projected_positions: dict[str, dict[str, Any]],
    baseline_total: Decimal,
    projected_total: Decimal,
) -> list[CoreSnapshotDeltaRecord]:
    return [
        _delta_record(
            security_id=security_id,
            baseline=_delta_position_values(
                position=baseline_positions.get(security_id),
                total=baseline_total,
            ),
            projected=_delta_position_values(
                position=projected_positions.get(security_id),
                total=projected_total,
            ),
        )
        for security_id in _delta_security_ids(
            baseline_positions=baseline_positions,
            projected_positions=projected_positions,
        )
    ]


def _position_record(*, item: dict[str, Any], weight: Decimal) -> CoreSnapshotPositionRecord:
    return CoreSnapshotPositionRecord(
        security_id=item["security_id"],
        quantity=item["quantity"],
        market_value_base=item["market_value_base"],
        market_value_local=item["market_value_local"],
        weight=weight,
        currency=item["currency"],
    )


def _delta_security_ids(
    *,
    baseline_positions: dict[str, dict[str, Any]],
    projected_positions: dict[str, dict[str, Any]],
) -> list[str]:
    return sorted(set(baseline_positions) | set(projected_positions))


def _delta_position_values(
    *,
    position: dict[str, Any] | None,
    total: Decimal,
) -> DeltaPositionValues:
    if position is None:
        return DeltaPositionValues(
            quantity=Decimal(0),
            market_value_base=Decimal(0),
            weight=Decimal(0),
        )
    market_value_base = position["market_value_base"]
    return DeltaPositionValues(
        quantity=position["quantity"],
        market_value_base=market_value_base,
        weight=_delta_weight(market_value_base=market_value_base, total=total),
    )


def _delta_weight(*, market_value_base: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal(0)
    return market_value_base / total


def _delta_record(
    *,
    security_id: str,
    baseline: DeltaPositionValues,
    projected: DeltaPositionValues,
) -> CoreSnapshotDeltaRecord:
    return CoreSnapshotDeltaRecord(
        security_id=security_id,
        baseline_quantity=baseline.quantity,
        projected_quantity=projected.quantity,
        delta_quantity=projected.quantity - baseline.quantity,
        baseline_market_value_base=baseline.market_value_base,
        projected_market_value_base=projected.market_value_base,
        delta_market_value_base=projected.market_value_base - baseline.market_value_base,
        delta_weight=projected.weight - baseline.weight,
    )
