"""Resolve market-data inputs and invoke pure portfolio-timeseries arithmetic."""

from datetime import date
from decimal import Decimal

from portfolio_common.domain.market_data.fx_rate import coerce_positive_fx_rate_or_none
from portfolio_common.domain.market_data.timeseries import TimeseriesFxRate

from ...domain.portfolio_timeseries.calculator import calculate_portfolio_timeseries
from ...domain.portfolio_timeseries.models import (
    PortfolioAggregationScope,
    PortfolioPositionContribution,
    PortfolioTimeseriesRecord,
)
from ...domain.position_timeseries.models import PositionTimeseriesRecord
from ...ports.timeseries_market_data import TimeseriesMarketDataPort
from .errors import (
    CurrencyReferenceNotFoundError,
    FxRateNotFoundError,
    InstrumentReferenceNotFoundError,
)


class CalculatePortfolioTimeseries:
    """Enrich position records with FX and calculate one complete portfolio day."""

    async def calculate_daily_record(
        self,
        portfolio: PortfolioAggregationScope,
        aggregation_date: date,
        epoch: int,
        position_timeseries: list[PositionTimeseriesRecord],
        repository: TimeseriesMarketDataPort,
    ) -> PortfolioTimeseriesRecord:
        """Resolve required source data before invoking pure domain arithmetic."""

        portfolio_currency = _normalize_currency(portfolio.base_currency)
        if not portfolio_currency:
            raise CurrencyReferenceNotFoundError(
                "Portfolio aggregation requires a portfolio reporting currency."
            )
        security_ids = list(
            dict.fromkeys(
                _normalize_security_id(position.security_id) for position in position_timeseries
            )
        )
        instruments = {
            _normalize_security_id(instrument.security_id): instrument
            for instrument in await repository.get_instruments_by_ids(security_ids)
        }
        fx_rate_cache: dict[tuple[str, str, date], TimeseriesFxRate] = {}
        contributions: list[PortfolioPositionContribution] = []

        for position in position_timeseries:
            security_id = _normalize_security_id(position.security_id)
            instrument = instruments.get(security_id)
            if instrument is None:
                raise InstrumentReferenceNotFoundError(
                    f"Missing instrument reference data for {security_id}."
                )
            instrument_currency = _normalize_currency(instrument.currency)
            if not instrument_currency:
                raise CurrencyReferenceNotFoundError(
                    f"Instrument reference data for {security_id} has no currency."
                )
            fx_rate = await _resolve_fx_rate(
                repository=repository,
                instrument_currency=instrument_currency,
                portfolio_currency=portfolio_currency,
                valuation_date=position.date,
                cache=fx_rate_cache,
            )
            contributions.append(
                PortfolioPositionContribution(
                    position_timeseries=position,
                    fx_rate=fx_rate,
                )
            )

        return calculate_portfolio_timeseries(
            portfolio=portfolio,
            aggregation_date=aggregation_date,
            epoch=epoch,
            contributions=contributions,
        )


def _normalize_currency(currency: object) -> str:
    return str(currency).strip().upper()


def _normalize_security_id(security_id: object) -> str:
    return str(security_id).strip()


async def _resolve_fx_rate(
    *,
    repository: TimeseriesMarketDataPort,
    instrument_currency: str,
    portfolio_currency: str,
    valuation_date: date,
    cache: dict[tuple[str, str, date], TimeseriesFxRate],
) -> TimeseriesFxRate:
    if instrument_currency == portfolio_currency:
        return TimeseriesFxRate(
            rate=Decimal("1"),
            from_currency=instrument_currency,
            to_currency=portfolio_currency,
            rate_date=valuation_date,
            source_record_id=None,
            source_updated_at=None,
        )

    cache_key = (instrument_currency, portfolio_currency, valuation_date)
    cached_rate = cache.get(cache_key)
    if cached_rate is not None:
        return cached_rate

    fx_rate = await repository.get_fx_rate(
        instrument_currency,
        portfolio_currency,
        valuation_date,
    )
    if fx_rate is None:
        raise FxRateNotFoundError(
            f"Missing FX rate from {instrument_currency} to {portfolio_currency} "
            f"for date {valuation_date}."
        )
    normalized_rate: Decimal | None = coerce_positive_fx_rate_or_none(fx_rate.rate)
    if normalized_rate is None:
        raise FxRateNotFoundError(
            f"Non-positive FX rate from {instrument_currency} to {portfolio_currency} "
            f"for date {valuation_date}."
        )

    if (
        _normalize_currency(fx_rate.from_currency) != instrument_currency
        or _normalize_currency(fx_rate.to_currency) != portfolio_currency
    ):
        raise FxRateNotFoundError(
            "FX rate source identity does not match requested pair "
            f"{instrument_currency} to {portfolio_currency}."
        )

    selected_rate = TimeseriesFxRate(
        rate=normalized_rate,
        from_currency=instrument_currency,
        to_currency=portfolio_currency,
        rate_date=fx_rate.rate_date,
        source_record_id=fx_rate.source_record_id,
        source_updated_at=fx_rate.source_updated_at,
    )
    cache[cache_key] = selected_rate
    return selected_rate
