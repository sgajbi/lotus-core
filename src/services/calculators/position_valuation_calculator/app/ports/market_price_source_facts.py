"""Application boundary for authoritative market-price source facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from portfolio_common.domain.valuation import (
    MarketPriceSourceFact,
    ValuationAuthorityScope,
)

MarketPriceAuthorityKey = tuple[str, str, str, date]


@dataclass(frozen=True, slots=True)
class MarketPriceAuthorityRequest:
    """One exact authority identity requested by position valuation."""

    scope: ValuationAuthorityScope
    price_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ValuationAuthorityScope):
            raise TypeError("scope must be a ValuationAuthorityScope")
        if type(self.price_date) is not date:
            raise TypeError("price_date must be an exact date")

    @property
    def key(self) -> MarketPriceAuthorityKey:
        return (*self.scope.key, self.price_date)


class MarketPriceSourceFactResolver(Protocol):
    """Bulk-resolve exact market-price authority without per-position reads."""

    async def resolve_many(
        self,
        requests: Sequence[MarketPriceAuthorityRequest],
    ) -> Mapping[MarketPriceAuthorityKey, MarketPriceSourceFact]: ...
