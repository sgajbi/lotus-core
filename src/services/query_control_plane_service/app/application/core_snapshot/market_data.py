"""Resolve effective-dated market data required by snapshot valuation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast

from portfolio_common.decimal_amounts import decimal_or_none
from portfolio_common.domain.currency import normalize_currency_code

from ...ports.core_snapshot import CoreSnapshotSourceReader
from .errors import CoreSnapshotUnavailableSectionError


async def get_fx_rate_or_raise(
    *,
    source_reader: CoreSnapshotSourceReader,
    from_currency: str,
    to_currency: str,
    as_of_date: date,
) -> Decimal:
    normalized_from_currency = normalize_currency_code(from_currency)
    normalized_to_currency = normalize_currency_code(to_currency)
    if normalized_from_currency == normalized_to_currency:
        return Decimal(1)
    rates = await source_reader.get_fx_rates(
        from_currency=normalized_from_currency,
        to_currency=normalized_to_currency,
        start_date=date.min,
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
