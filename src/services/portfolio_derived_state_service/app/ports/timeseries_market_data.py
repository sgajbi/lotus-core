"""Market-data read capability required by portfolio timeseries aggregation."""

from datetime import date
from typing import Protocol

from portfolio_common.domain.market_data.timeseries import (
    TimeseriesFxRate,
    TimeseriesInstrument,
)


class TimeseriesMarketDataPort(Protocol):
    """Provide normalized instrument and FX records without persistence models."""

    async def get_instruments_by_ids(
        self,
        security_ids: list[str],
    ) -> list[TimeseriesInstrument]: ...

    async def get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        a_date: date,
    ) -> TimeseriesFxRate | None: ...
