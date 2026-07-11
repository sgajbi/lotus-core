"""Read port for canonical index series windows."""

from datetime import date
from typing import Protocol

from ..domain.index_series import IndexPriceEvidence, IndexReturnEvidence


class IndexSeriesReader(Protocol):
    """Read canonical index observations without exposing persistence models."""

    async def list_prices(
        self, *, index_id: str, start_date: date, end_date: date
    ) -> list[IndexPriceEvidence]: ...

    async def list_returns(
        self, *, index_id: str, start_date: date, end_date: date
    ) -> list[IndexReturnEvidence]: ...
