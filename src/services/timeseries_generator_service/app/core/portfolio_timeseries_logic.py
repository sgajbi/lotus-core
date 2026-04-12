# src/services/timeseries_generator_service/app/core/portfolio_timeseries_logic.py
import logging
from datetime import date
from decimal import Decimal
from typing import List

from portfolio_common.database_models import (
    Portfolio,
    PortfolioTimeseries,
    PositionTimeseries,
)

from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)


class FxRateNotFoundError(Exception):
    """Raised when a required FX rate for a calculation is not found."""

    pass


class PortfolioTimeseriesLogic:
    """
    A stateless calculator for aggregating position data into a single daily
    portfolio time series record, handling all necessary FX conversions.
    """

    @staticmethod
    async def calculate_daily_record(
        portfolio: Portfolio,
        a_date: date,
        epoch: int,
        position_timeseries_list: List[PositionTimeseries],
        repo: TimeseriesRepository,
    ) -> PortfolioTimeseries:
        """
        Calculates a single, complete portfolio time series record for a given day and epoch.
        """
        total_bod_mv = Decimal(0)
        total_bod_cf = Decimal(0)
        total_eod_cf = Decimal(0)
        total_eod_mv = Decimal(0)
        total_fees = Decimal(0)

        portfolio_currency = PortfolioTimeseriesLogic._normalize_currency(portfolio.base_currency)
        fx_rate_cache: dict[tuple[str, str, date], Decimal] = {}

        # 1. Aggregate market values and portfolio-level cashflows directly from the
        # same position-timeseries rows. This keeps portfolio BOD/EOD aligned with
        # the summed position-timeseries contract instead of relying on a separate
        # previous-portfolio carry-forward path.
        security_ids = list(dict.fromkeys(pt.security_id for pt in position_timeseries_list))
        instruments_list = await repo.get_instruments_by_ids(security_ids)
        instruments = {inst.security_id: inst for inst in instruments_list}

        for pos_ts in position_timeseries_list:
            instrument = instruments.get(pos_ts.security_id)
            if not instrument:
                logger.warning(
                    f"Could not find instrument {pos_ts.security_id}. Skipping its contribution."
                )
                continue

            instrument_currency = PortfolioTimeseriesLogic._normalize_currency(instrument.currency)
            rate = await PortfolioTimeseriesLogic._resolve_fx_rate(
                repo=repo,
                instrument_currency=instrument_currency,
                portfolio_currency=portfolio_currency,
                valuation_date=pos_ts.date,
                fx_rate_cache=fx_rate_cache,
            )

            total_bod_mv += (pos_ts.bod_market_value or Decimal(0)) * rate
            total_bod_cf += (pos_ts.bod_cashflow_portfolio or Decimal(0)) * rate
            total_eod_mv += (pos_ts.eod_market_value or Decimal(0)) * rate
            total_eod_cf += (pos_ts.eod_cashflow_portfolio or Decimal(0)) * rate

            if (pos_ts.bod_cashflow_portfolio or Decimal(0)) < 0:
                total_fees += abs(pos_ts.bod_cashflow_portfolio * rate)
            if (pos_ts.eod_cashflow_portfolio or Decimal(0)) < 0:
                total_fees += abs(pos_ts.eod_cashflow_portfolio * rate)

        return PortfolioTimeseries(
            portfolio_id=portfolio.portfolio_id,
            date=a_date,
            epoch=epoch,
            bod_market_value=total_bod_mv,
            bod_cashflow=total_bod_cf,
            eod_cashflow=total_eod_cf,
            eod_market_value=total_eod_mv,
            fees=total_fees,
        )

    @staticmethod
    def _normalize_currency(currency: object) -> str:
        return str(currency).strip().upper()

    @staticmethod
    async def _resolve_fx_rate(
        repo: TimeseriesRepository,
        instrument_currency: str,
        portfolio_currency: str,
        valuation_date: date,
        fx_rate_cache: dict[tuple[str, str, date], Decimal],
    ) -> Decimal:
        if instrument_currency == portfolio_currency:
            return Decimal("1")

        cache_key = (instrument_currency, portfolio_currency, valuation_date)
        cached_rate = fx_rate_cache.get(cache_key)
        if cached_rate is not None:
            return cached_rate

        fx_rate = await repo.get_fx_rate(instrument_currency, portfolio_currency, valuation_date)
        if not fx_rate:
            error_msg = (
                f"Missing FX rate from {instrument_currency} "
                f"to {portfolio_currency} for date {valuation_date}."
            )
            logger.error(error_msg)
            raise FxRateNotFoundError(error_msg)

        fx_rate_cache[cache_key] = fx_rate.rate
        return fx_rate.rate
