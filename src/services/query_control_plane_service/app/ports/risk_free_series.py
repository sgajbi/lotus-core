"""Read port for canonical risk-free series windows."""

from datetime import date
from typing import Protocol

from ..domain.risk_free_series import RiskFreeRateEvidence


class RiskFreeSeriesReader(Protocol):
    """Read risk-free observations without exposing persistence models."""

    async def list_rates(
        self, *, currency: str, start_date: date, end_date: date
    ) -> list[RiskFreeRateEvidence]: ...
