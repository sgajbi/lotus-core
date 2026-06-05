from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..repositories.identifier_normalization import normalize_security_id
from .control_code_normalization import normalize_control_code
from .decimal_amounts import decimal_or_none, decimal_or_zero

CASH_ASSET_CLASS = "CASH"


def baseline_position_entries(
    *,
    rows: list[Any],
    use_snapshot: bool,
    reporting_fx: Decimal,
    include_cash: bool,
    include_zero: bool,
) -> dict[str, dict[str, Any]]:
    baseline: dict[str, dict[str, Any]] = {}
    for row, instrument, _state in rows:
        entry = baseline_position_entry(
            row=row,
            instrument=instrument,
            use_snapshot=use_snapshot,
            reporting_fx=reporting_fx,
            include_cash=include_cash,
            include_zero=include_zero,
        )
        if entry is not None:
            baseline[entry["security_id"]] = entry
    return dict(sorted(baseline.items(), key=lambda item: item[0]))


def baseline_position_entry(
    *,
    row: Any,
    instrument: Any,
    use_snapshot: bool,
    reporting_fx: Decimal,
    include_cash: bool,
    include_zero: bool,
) -> dict[str, Any] | None:
    quantity = decimal_or_zero(row.quantity)
    if skip_baseline_position(
        quantity=quantity,
        instrument=instrument,
        include_cash=include_cash,
        include_zero=include_zero,
    ):
        return None
    security_id = normalize_security_id(row.security_id)
    if not security_id:
        return None
    market_value_base, market_value_local = baseline_market_values(
        row=row,
        use_snapshot=use_snapshot,
        reporting_fx=reporting_fx,
    )
    return baseline_position_payload(
        security_id=security_id,
        quantity=quantity,
        market_value_base=market_value_base,
        market_value_local=market_value_local,
        instrument=instrument,
    )


def skip_baseline_position(
    *,
    quantity: Decimal,
    instrument: Any,
    include_cash: bool,
    include_zero: bool,
) -> bool:
    if not include_zero and quantity == Decimal(0):
        return True
    return (
        not include_cash and instrument is not None and is_cash_asset_class(instrument.asset_class)
    )


def baseline_market_values(
    *,
    row: Any,
    use_snapshot: bool,
    reporting_fx: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    if use_snapshot:
        market_value_base_raw = decimal_or_none(row.market_value)
        market_value_local = decimal_or_none(row.market_value_local)
    else:
        market_value_base_raw = decimal_or_none(row.cost_basis)
        market_value_local = decimal_or_none(row.cost_basis_local)
    market_value_base = (
        market_value_base_raw * reporting_fx if market_value_base_raw is not None else None
    )
    return market_value_base, market_value_local


def baseline_position_payload(
    *,
    security_id: str,
    quantity: Decimal,
    market_value_base: Decimal | None,
    market_value_local: Decimal | None,
    instrument: Any,
) -> dict[str, Any]:
    payload = {
        "security_id": security_id,
        "quantity": quantity,
        "market_value_base": market_value_base,
        "market_value_local": market_value_local,
    }
    if instrument is None:
        payload.update(missing_instrument_payload(security_id))
    else:
        payload.update(baseline_instrument_payload(instrument))
    return payload


def missing_instrument_payload(security_id: str) -> dict[str, Any]:
    return {
        "currency": None,
        "instrument_name": security_id,
        "asset_class": None,
        "sector": None,
        "country_of_risk": None,
        "isin": None,
        "issuer_id": None,
        "issuer_name": None,
        "ultimate_parent_issuer_id": None,
        "ultimate_parent_issuer_name": None,
        "liquidity_tier": None,
    }


def baseline_instrument_payload(instrument: Any) -> dict[str, Any]:
    return {
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


def is_cash_asset_class(value: Any) -> bool:
    return normalize_control_code(value) == CASH_ASSET_CLASS
