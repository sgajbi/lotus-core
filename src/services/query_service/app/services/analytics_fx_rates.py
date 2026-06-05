from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..repositories.currency_codes import normalize_currency_code


class AnalyticsFxRateError(RuntimeError):
    pass


async def get_portfolio_to_reporting_rates(
    repo: object,
    *,
    portfolio_currency: str,
    reporting_currency: str,
    start_date: date,
    end_date: date,
) -> dict[date, Decimal]:
    normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
    normalized_reporting_currency = normalize_currency_code(reporting_currency)
    if normalized_portfolio_currency == normalized_reporting_currency:
        return {}
    return await repo.get_fx_rates_map(
        from_currency=normalized_portfolio_currency,
        to_currency=normalized_reporting_currency,
        start_date=start_date,
        end_date=end_date,
    )


async def get_position_to_portfolio_rate_maps(
    repo: object,
    *,
    position_currencies: set[str],
    portfolio_currency: str,
    start_date: date,
    end_date: date,
) -> dict[str, dict[date, Decimal]]:
    normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
    normalized_position_currencies = {
        normalize_currency_code(position_currency)
        for position_currency in position_currencies
        if position_currency
    }
    rates: dict[str, dict[date, Decimal]] = {}
    for position_currency in sorted(normalized_position_currencies):
        if position_currency == normalized_portfolio_currency:
            rates[position_currency] = {}
            continue
        rates[position_currency] = await repo.get_fx_rates_map(
            from_currency=position_currency,
            to_currency=normalized_portfolio_currency,
            start_date=start_date,
            end_date=end_date,
        )
    return rates


def position_to_portfolio_rate(
    *,
    position_currency: str,
    portfolio_currency: str,
    valuation_date: date,
    position_to_portfolio_rates: dict[str, dict[date, Decimal]],
) -> Decimal:
    if position_currency == portfolio_currency:
        return Decimal("1")
    rate_map = position_to_portfolio_rates.get(position_currency, {})
    if valuation_date not in rate_map:
        raise AnalyticsFxRateError(
            f"Missing FX rate for {position_currency}/{portfolio_currency} on {valuation_date}."
        )
    return rate_map[valuation_date]


def portfolio_to_reporting_rate(
    *,
    portfolio_currency: str,
    reporting_currency: str,
    valuation_date: date,
    fx_rates: dict[date, Decimal],
) -> Decimal:
    if reporting_currency == portfolio_currency:
        return Decimal("1")
    if valuation_date not in fx_rates:
        raise AnalyticsFxRateError(
            f"Missing FX rate for {portfolio_currency}/{reporting_currency} on {valuation_date}."
        )
    return fx_rates[valuation_date]
