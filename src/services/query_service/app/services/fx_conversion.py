from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any

from ..repositories.currency_codes import normalize_currency_code
from .decimal_amounts import decimal_or_none


class CachedFxRateConverter:
    def __init__(self, repo: Any) -> None:
        self._repo = repo
        self._cache: dict[tuple[str, str, date], Decimal] = {}
        self._inflight: dict[tuple[str, str, date], asyncio.Task[Decimal]] = {}

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
        task = self._inflight.get(cache_key)
        if task is None:
            task = asyncio.create_task(
                self._load_fx_rate(
                    from_currency=normalized_from_currency,
                    to_currency=normalized_to_currency,
                    as_of_date=as_of_date,
                    cache_key=cache_key,
                )
            )
            self._inflight[cache_key] = task
            task.add_done_callback(
                lambda completed_task: self._clear_inflight(cache_key, completed_task)
            )
        return await asyncio.shield(task)

    async def _load_fx_rate(
        self,
        *,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
        cache_key: tuple[str, str, date],
    ) -> Decimal:
        rate = await self._repo.get_latest_fx_rate(
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )
        resolved_rate = decimal_or_none(rate)
        if resolved_rate is None:
            raise ValueError(
                f"FX rate not found for {from_currency}/{to_currency} as of {as_of_date}."
            )
        self._cache[cache_key] = resolved_rate
        return resolved_rate

    def _clear_inflight(
        self,
        cache_key: tuple[str, str, date],
        completed_task: asyncio.Future[Decimal],
    ) -> None:
        if self._inflight.get(cache_key) is completed_task:
            self._inflight.pop(cache_key, None)
