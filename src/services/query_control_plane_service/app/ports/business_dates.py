"""Business-date lookup port for capability contract assembly."""

from __future__ import annotations

from datetime import date
from typing import Protocol


class BusinessDateProvider(Protocol):
    """Resolve the latest governed business date when source data is available."""

    def latest_business_date(self) -> date | None:
        """Return the latest governed date, or none when source data is unavailable."""
