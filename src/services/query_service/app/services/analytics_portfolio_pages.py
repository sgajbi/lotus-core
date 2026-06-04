from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..repositories.currency_codes import normalize_currency_code


class AnalyticsPortfolioPageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PortfolioObservationPageScope:
    page_dates: list[date]
    has_more: bool


def portfolio_observation_page_scope(
    *,
    observed_dates: list[date],
    cursor_date: date | None,
    page_size: int,
) -> PortfolioObservationPageScope:
    paged_dates = [day for day in observed_dates if cursor_date is None or day > cursor_date]
    return PortfolioObservationPageScope(
        page_dates=paged_dates[:page_size],
        has_more=len(paged_dates) > page_size,
    )


def portfolio_row_buckets(
    *,
    page_dates: list[date],
    position_rows: list[object],
) -> dict[date, list[object]]:
    page_date_set = set(page_dates)
    row_buckets: dict[date, list[object]] = defaultdict(list)
    for row in position_rows:
        if row.valuation_date in page_date_set:
            row_buckets[row.valuation_date].append(row)
    return row_buckets


def portfolio_to_reporting_observation_rate(
    *,
    valuation_date: date,
    portfolio_currency: str,
    reporting_currency: str,
    portfolio_to_reporting_rates: dict[date, Decimal],
) -> Decimal:
    if reporting_currency == portfolio_currency:
        return Decimal("1")
    if valuation_date not in portfolio_to_reporting_rates:
        raise AnalyticsPortfolioPageError(
            f"Missing FX rate for {portfolio_currency}/{reporting_currency} on {valuation_date}."
        )
    return portfolio_to_reporting_rates[valuation_date]


def position_to_portfolio_observation_rate(
    *,
    row: object,
    valuation_date: date,
    portfolio_currency: str,
    position_to_portfolio_rates: dict[str, dict[date, Decimal]],
) -> Decimal:
    position_currency = (
        normalize_currency_code(str(getattr(row, "position_currency")))
        if getattr(row, "position_currency", None)
        else ""
    )
    if not position_currency or position_currency == portfolio_currency:
        return Decimal("1")
    rate_map = position_to_portfolio_rates.get(position_currency, {})
    if valuation_date not in rate_map:
        raise AnalyticsPortfolioPageError(
            f"Missing FX rate for {position_currency}/{portfolio_currency} on {valuation_date}."
        )
    return rate_map[valuation_date]


def portfolio_observation_next_page_token(
    *,
    page_scope: PortfolioObservationPageScope,
    snapshot_epoch: int,
    request_scope_fingerprint: str,
    encode_page_token: Callable[[dict], str],
) -> str | None:
    if not page_scope.has_more:
        return None
    return encode_page_token(
        {
            "valuation_date": page_scope.page_dates[-1].isoformat(),
            "snapshot_epoch": snapshot_epoch,
            "scope_fingerprint": request_scope_fingerprint,
        }
    )
