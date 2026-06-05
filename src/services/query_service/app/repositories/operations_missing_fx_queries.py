from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import Portfolio, Transaction
from sqlalchemy import Date, cast, func, select

from .currency_codes import currency_code_sql_expr, normalize_currency_code
from .date_filters import start_of_next_day
from .identifier_normalization import normalize_security_id
from .operations_health_queries import int_or_zero
from .operations_models import (
    MissingHistoricalFxDependencyRecord,
    MissingHistoricalFxDependencySummary,
)


def missing_historical_fx_base_stmt(
    *,
    portfolio_id: str,
    as_of_date: date,
    snapshot_as_of: datetime | None = None,
):
    trade_currency = currency_code_sql_expr(Transaction.trade_currency)
    portfolio_currency = currency_code_sql_expr(Portfolio.base_currency)
    stmt = (
        select(
            Transaction.transaction_id.label("transaction_id"),
            func.trim(Transaction.security_id).label("security_id"),
            cast(Transaction.transaction_date, Date).label("transaction_date"),
            trade_currency.label("trade_currency"),
            portfolio_currency.label("portfolio_currency"),
        )
        .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
        .where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.transaction_date < start_of_next_day(as_of_date),
            trade_currency != portfolio_currency,
            Transaction.transaction_fx_rate.is_(None),
        )
    )
    if snapshot_as_of is not None:
        stmt = stmt.where(Transaction.created_at <= snapshot_as_of)
    return stmt


def missing_historical_fx_aggregate_stmt(base_subq):
    return select(
        func.count().label("missing_count"),
        func.min(base_subq.c.transaction_date).label("earliest_transaction_date"),
        func.max(base_subq.c.transaction_date).label("latest_transaction_date"),
    )


def missing_historical_fx_sample_stmt(base_subq, *, sample_limit: int):
    return (
        select(base_subq)
        .order_by(
            base_subq.c.transaction_date.asc(),
            base_subq.c.transaction_id.asc(),
        )
        .limit(sample_limit)
    )


def missing_historical_fx_record_from_row(row) -> MissingHistoricalFxDependencyRecord:
    return MissingHistoricalFxDependencyRecord(
        transaction_id=row.transaction_id,
        security_id=normalize_security_id(row.security_id),
        transaction_date=row.transaction_date,
        trade_currency=normalize_currency_code(row.trade_currency or ""),
        portfolio_currency=normalize_currency_code(row.portfolio_currency or ""),
    )


def missing_historical_fx_summary_from_rows(
    aggregate_row,
    sample_rows,
) -> MissingHistoricalFxDependencySummary:
    return MissingHistoricalFxDependencySummary(
        missing_count=int_or_zero(aggregate_row.missing_count),
        earliest_transaction_date=aggregate_row.earliest_transaction_date,
        latest_transaction_date=aggregate_row.latest_transaction_date,
        sample_records=[missing_historical_fx_record_from_row(row) for row in sample_rows],
    )
