"""Framework-neutral market-data records used by timeseries calculations."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TimeseriesInstrument:
    """Instrument identity and currency required for timeseries conversion."""

    security_id: str
    currency: str


@dataclass(frozen=True, slots=True)
class TimeseriesFxRate:
    """Selected FX fact and persisted identity used by timeseries conversion."""

    rate: Decimal
    from_currency: str
    to_currency: str
    rate_date: date
    source_record_id: int | None
    source_updated_at: datetime | None
