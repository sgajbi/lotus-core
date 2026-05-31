from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ..repositories.currency_codes import normalize_currency_code


class CachedFxRateConverter:
    def __init__(self, repo: Any) -> None:
        self._repo = repo
        self._cache: dict[tuple[str, str, date], Decimal] = {}

    async def convert_amount(
        self,
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        if normalized_from_currency == normalized_to_currency:
            return amount
        rate = await self.get_fx_rate(
            normalized_from_currency,
            normalized_to_currency,
            as_of_date,
        )
        return amount * rate

    async def get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        cache_key = (normalized_from_currency, normalized_to_currency, as_of_date)
        if cache_key in self._cache:
            return self._cache[cache_key]
        rate = await self._repo.get_latest_fx_rate(
            from_currency=normalized_from_currency,
            to_currency=normalized_to_currency,
            as_of_date=as_of_date,
        )
        if rate is None:
            raise ValueError(
                "FX rate not found for "
                f"{normalized_from_currency}/{normalized_to_currency} as of {as_of_date}."
            )
        resolved_rate = Decimal(str(rate))
        self._cache[cache_key] = resolved_rate
        return resolved_rate
