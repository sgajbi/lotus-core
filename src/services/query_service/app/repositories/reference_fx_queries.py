from __future__ import annotations

from datetime import date
from typing import Any

from portfolio_common.database_models import FxRate
from sqlalchemy import and_, func, select, tuple_

from .currency_codes import currency_code_sql_expr, normalize_currency_code


def normalized_currency_pairs(currency_pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    normalized_pairs = [
        (normalized_base, normalized_quote)
        for base, quote in currency_pairs
        if (normalized_base := normalize_currency_code(base))
        and (normalized_quote := normalize_currency_code(quote))
    ]
    return list(dict.fromkeys(normalized_pairs))


def latest_fx_rates_stmt(
    *,
    normalized_pairs: list[tuple[str, str]],
    as_of_date: date,
):
    from_currency_expr = currency_code_sql_expr(FxRate.from_currency)
    to_currency_expr = currency_code_sql_expr(FxRate.to_currency)
    latest_rate_dates = _latest_fx_rate_dates_subquery(
        normalized_pairs=normalized_pairs,
        as_of_date=as_of_date,
        from_currency_expr=from_currency_expr,
        to_currency_expr=to_currency_expr,
    )
    return (
        select(FxRate)
        .join(
            latest_rate_dates,
            and_(
                from_currency_expr == latest_rate_dates.c.from_currency,
                to_currency_expr == latest_rate_dates.c.to_currency,
                FxRate.rate_date == latest_rate_dates.c.latest_rate_date,
            ),
        )
        .order_by(from_currency_expr.asc(), to_currency_expr.asc())
    )


def _latest_fx_rate_dates_subquery(
    *,
    normalized_pairs: list[tuple[str, str]],
    as_of_date: date,
    from_currency_expr: Any,
    to_currency_expr: Any,
):
    return (
        select(
            from_currency_expr.label("from_currency"),
            to_currency_expr.label("to_currency"),
            func.max(FxRate.rate_date).label("latest_rate_date"),
        )
        .where(
            tuple_(from_currency_expr, to_currency_expr).in_(normalized_pairs),
            FxRate.rate_date <= as_of_date,
        )
        .group_by(from_currency_expr, to_currency_expr)
        .subquery()
    )
