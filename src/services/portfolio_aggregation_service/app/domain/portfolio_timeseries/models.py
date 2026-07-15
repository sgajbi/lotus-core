"""Immutable domain inputs for portfolio-timeseries calculation."""

from dataclasses import dataclass
from decimal import Decimal

from ..aggregation_records import PositionTimeseriesRecord
from .errors import InvalidPortfolioPositionContribution


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioPositionContribution:
    """Pair one position-day record with its portfolio-currency FX rate."""

    position_timeseries: PositionTimeseriesRecord
    fx_rate_to_portfolio_currency: Decimal

    def __post_init__(self) -> None:
        security_id = self.position_timeseries.security_id.strip()
        if not security_id:
            raise InvalidPortfolioPositionContribution(
                "Portfolio position contribution requires a security identity."
            )
        if self.fx_rate_to_portfolio_currency <= 0:
            raise InvalidPortfolioPositionContribution(
                "Portfolio position contribution requires a positive FX rate."
            )
