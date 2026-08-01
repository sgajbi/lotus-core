"""Immutable inputs and outputs for portfolio-timeseries calculation."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import CalculationLineage
from portfolio_common.domain.market_data.timeseries import TimeseriesFxRate

from ..position_timeseries.models import PositionTimeseriesRecord
from .errors import InvalidPortfolioPositionContribution


@dataclass(frozen=True, slots=True)
class PortfolioAggregationScope:
    """Portfolio identity and reporting currency required for aggregation."""

    portfolio_id: str
    base_currency: str


@dataclass(frozen=True, slots=True)
class PortfolioTimeseriesRecord:
    """Calculated portfolio-day economics ready for persistence."""

    portfolio_id: str
    date: date
    epoch: int
    bod_market_value: Decimal
    bod_cashflow: Decimal
    eod_cashflow: Decimal
    eod_market_value: Decimal
    fees: Decimal
    calculation_lineage: CalculationLineage | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioPositionContribution:
    """Pair one position-day record with its selected portfolio-currency FX fact."""

    position_timeseries: PositionTimeseriesRecord
    fx_rate: TimeseriesFxRate

    def __post_init__(self) -> None:
        security_id = self.position_timeseries.security_id.strip()
        if not security_id:
            raise InvalidPortfolioPositionContribution(
                "Portfolio position contribution requires a security identity."
            )
        if self.fx_rate.rate <= 0:
            raise InvalidPortfolioPositionContribution(
                "Portfolio position contribution requires a positive FX rate."
            )
        if not self.fx_rate.from_currency.strip() or not self.fx_rate.to_currency.strip():
            raise InvalidPortfolioPositionContribution(
                "Portfolio position contribution requires an FX currency pair."
            )
        is_identity_conversion = (
            self.fx_rate.from_currency.strip().upper() == self.fx_rate.to_currency.strip().upper()
        )
        if is_identity_conversion:
            if self.fx_rate.rate != Decimal("1"):
                raise InvalidPortfolioPositionContribution(
                    "Same-currency portfolio contributions require an identity FX rate."
                )
            if (
                self.fx_rate.source_record_id is not None
                or self.fx_rate.source_updated_at is not None
            ):
                raise InvalidPortfolioPositionContribution(
                    "Same-currency portfolio contributions cannot cite a persisted FX fact."
                )
            return
        if self.fx_rate.source_record_id is None or self.fx_rate.source_record_id < 1:
            raise InvalidPortfolioPositionContribution(
                "Cross-currency portfolio contributions require a persisted FX record identity."
            )
        source_updated_at = self.fx_rate.source_updated_at
        if (
            source_updated_at is None
            or source_updated_at.tzinfo is None
            or source_updated_at.utcoffset() is None
        ):
            raise InvalidPortfolioPositionContribution(
                "Cross-currency portfolio contributions require an aware FX source revision."
            )


@dataclass(frozen=True, slots=True)
class PortfolioAggregationCompletion:
    """Portfolio-day aggregation identity ready for durable event staging."""

    portfolio_id: str
    aggregation_date: date
    epoch: int
    aggregation_revision: int

    def __post_init__(self) -> None:
        if self.aggregation_revision < 1:
            raise ValueError("Portfolio aggregation completion revision must be positive.")
