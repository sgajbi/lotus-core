from __future__ import annotations

from decimal import Decimal
from typing import Any

from .core_snapshot_baseline_positions import is_cash_asset_class
from .position_flow_effects import transaction_quantity_effect_decimal


def baseline_projected_positions(
    baseline_positions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {key: baseline_projected_position(value) for key, value in baseline_positions.items()}


def baseline_projected_position(value: dict[str, Any]) -> dict[str, Any]:
    projected_value = dict(value)
    projected_value["baseline_quantity"] = projected_value["quantity"]
    return projected_value


def missing_projected_security_ids(
    projected: dict[str, dict[str, Any]],
    normalized_changes: list[tuple[str, Any]],
) -> list[str]:
    changed_security_ids = {security_id for security_id, _change in normalized_changes}
    return [sid for sid in changed_security_ids if sid not in projected]


def new_projected_position(security_id: str, instrument: Any) -> dict[str, Any]:
    return {
        "security_id": security_id,
        "quantity": Decimal(0),
        "baseline_quantity": Decimal(0),
        "market_value_base": Decimal(0),
        "market_value_local": Decimal(0),
        "currency": instrument.currency,
        "instrument_name": instrument.name,
        "asset_class": instrument.asset_class,
        "sector": instrument.sector,
        "country_of_risk": instrument.country_of_risk,
        "isin": instrument.isin,
        "issuer_id": instrument.issuer_id,
        "issuer_name": instrument.issuer_name,
        "ultimate_parent_issuer_id": instrument.ultimate_parent_issuer_id,
        "ultimate_parent_issuer_name": instrument.ultimate_parent_issuer_name,
        "liquidity_tier": instrument.liquidity_tier,
    }


def apply_projected_position_changes(
    projected: dict[str, dict[str, Any]],
    normalized_changes: list[tuple[str, Any]],
) -> None:
    for security_id, change in normalized_changes:
        entry = projected[security_id]
        entry["quantity"] = entry["quantity"] + change_quantity_effect(change)


def apply_baseline_projected_values(
    projected: dict[str, dict[str, Any]],
    *,
    include_cash: bool,
    include_zero: bool,
) -> dict[str, tuple[dict[str, Any], Decimal]]:
    price_required: dict[str, tuple[dict[str, Any], Decimal]] = {}
    for security_id, entry in projected.items():
        if skip_projected_position(entry, include_cash=include_cash, include_zero=include_zero):
            continue
        if apply_baseline_projected_value(entry):
            continue
        quantity = entry["quantity"]
        if quantity <= 0:
            entry["market_value_base"] = Decimal(0)
            entry["market_value_local"] = Decimal(0)
            continue
        price_required[security_id] = (entry, quantity)
    return price_required


def apply_baseline_projected_value(entry: dict[str, Any]) -> bool:
    baseline_qty = entry["baseline_quantity"]
    if baseline_qty <= 0 or entry.get("market_value_base") is None:
        return False
    unit_base = entry["market_value_base"] / baseline_qty
    entry["market_value_base"] = unit_base * entry["quantity"]
    if entry.get("market_value_local") is not None:
        unit_local = entry["market_value_local"] / baseline_qty
        entry["market_value_local"] = unit_local * entry["quantity"]
    return True


def filtered_projected_positions(
    projected: dict[str, dict[str, Any]],
    *,
    include_cash: bool,
    include_zero: bool,
) -> dict[str, dict[str, Any]]:
    return {
        key: value
        for key, value in projected.items()
        if not skip_projected_position(
            value,
            include_cash=include_cash,
            include_zero=include_zero,
        )
    }


def skip_projected_position(
    entry: dict[str, Any],
    *,
    include_cash: bool,
    include_zero: bool,
) -> bool:
    if not include_cash and is_cash_asset_class(entry.get("asset_class")):
        return True
    return not include_zero and entry["quantity"] == Decimal(0)


def change_quantity_effect(change: Any) -> Decimal:
    return transaction_quantity_effect_decimal(
        transaction_type=getattr(change, "transaction_type", None),
        quantity=getattr(change, "quantity", None),
        amount=getattr(change, "amount", None),
    )
