"""Read port for dated market FX evidence."""

from datetime import date
from typing import Protocol

from ..domain.market_fx import FxRateEvidence, FxSourceSelection


class MarketFxRateReader(Protocol):
    """Read canonical FX rates without exposing persistence models."""

    async def list_rates(
        self,
        *,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> list[FxRateEvidence]: ...

    async def list_source_rates(
        self,
        *,
        selection: FxSourceSelection,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> list[FxRateEvidence]: ...
