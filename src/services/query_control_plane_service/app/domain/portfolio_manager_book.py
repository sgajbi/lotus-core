"""Domain records for portfolio-manager book membership."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class PortfolioManagerBookRecord:
    """Persistence-independent portfolio-master membership evidence."""

    portfolio_id: str
    client_id: str
    booking_center_code: str
    portfolio_type: str
    status: str
    open_date: date
    close_date: date | None
    base_currency: str
    created_at: datetime | None
    updated_at: datetime | None
