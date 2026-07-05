from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from ..repositories.currency_codes import normalize_currency_code
from .core_snapshot_errors import CoreSnapshotUnavailableSectionError
from .decimal_amounts import decimal_or_none


async def get_fx_rate_or_raise(
    *,
    fx_repo: Any,
    from_currency: str,
    to_currency: str,
    as_of_date: Any,
) -> Decimal:
    normalized_from_currency = normalize_currency_code(from_currency)
    normalized_to_currency = normalize_currency_code(to_currency)
    if normalized_from_currency == normalized_to_currency:
        return Decimal(1)
    rates = await fx_repo.get_fx_rates(
        from_currency=normalized_from_currency,
        to_currency=normalized_to_currency,
        end_date=as_of_date,
    )
    pair = f"{normalized_from_currency}/{normalized_to_currency}"
    message = f"missing FX rate {pair} on or before {as_of_date.isoformat()}"
    if not rates:
        raise CoreSnapshotUnavailableSectionError(message)
    return required_decimal(rates[-1].rate, message=message)


def required_decimal(value: Any, *, message: str) -> Decimal:
    resolved_value = decimal_or_none(value)
    if resolved_value is None:
        raise CoreSnapshotUnavailableSectionError(message)
    return cast(Decimal, resolved_value)
