"""Framework-neutral market-data records used by timeseries calculations."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TimeseriesInstrument:
    """Instrument identity and currency required for timeseries conversion."""

    security_id: str
    currency: str


@dataclass(frozen=True, slots=True)
class TimeseriesFxRate:
    """FX rate value required for timeseries conversion."""

    rate: Decimal
