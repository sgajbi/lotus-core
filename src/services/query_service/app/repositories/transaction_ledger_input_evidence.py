"""Bounded SQL evidence for complete TransactionLedgerWindow input scopes."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from portfolio_common.database_models import Cashflow, FxRate, Transaction, TransactionCost
from sqlalchemy import String, Text, cast, func, literal, select, true, union
from sqlalchemy.dialects.postgresql import aggregate_order_by

from .currency_query_expressions import currency_code_sql_expr


def _model_values(model: Any, *, exclude: Iterable[str] = ()) -> tuple[Any, ...]:
    excluded = frozenset(exclude)
    return tuple(
        getattr(model, column.name)
        for column in model.__table__.columns
        if column.name not in excluded
    )


def _ordered_jsonb_digest(*, values: tuple[Any, ...], order_by: tuple[Any, ...]) -> Any:
    """Return one fixed-width digest without returning source rows to the application."""

    payload = func.jsonb_build_array(*values)
    row_bytes = func.convert_to(cast(payload, Text), literal("UTF8"))
    row_digest = func.encode(func.sha256(row_bytes), literal("hex"))
    ordered_row_digests = func.string_agg(
        row_digest,
        aggregate_order_by(literal(""), *order_by),
    )
    canonical_bytes = func.convert_to(ordered_row_digests, literal("UTF8"))
    return func.encode(func.sha256(canonical_bytes), literal("hex"))


def _transaction_aggregate(matching_transactions: Any) -> Any:
    return (
        select(
            func.count(Transaction.id).label("transaction_count"),
            func.max(Transaction.updated_at).label("transaction_latest_at"),
            _ordered_jsonb_digest(
                values=_model_values(Transaction, exclude=("id",)),
                order_by=(Transaction.transaction_id.asc(), Transaction.id.asc()),
            ).label("transaction_digest"),
        )
        .join(
            matching_transactions,
            matching_transactions.c.transaction_pk == Transaction.id,
        )
        .subquery("transaction_ledger_transaction_evidence")
    )


def _transaction_cost_aggregate(matching_transactions: Any) -> Any:
    return (
        select(
            func.max(TransactionCost.updated_at).label("transaction_cost_latest_at"),
            _ordered_jsonb_digest(
                values=_model_values(TransactionCost, exclude=("id",)),
                order_by=(
                    TransactionCost.transaction_id.asc(),
                    TransactionCost.fee_type.asc(),
                    TransactionCost.id.asc(),
                ),
            ).label("transaction_cost_digest"),
        )
        .join(
            matching_transactions,
            matching_transactions.c.transaction_id == TransactionCost.transaction_id,
        )
        .subquery("transaction_ledger_cost_evidence")
    )


def _selected_cashflow_aggregate(matching_transactions: Any) -> Any:
    ranked_cashflows = (
        select(
            *Cashflow.__table__.columns,
            func.row_number()
            .over(
                partition_by=Cashflow.transaction_id,
                order_by=(Cashflow.epoch.desc(), Cashflow.id.desc()),
            )
            .label("selection_rank"),
        )
        .join(
            matching_transactions,
            matching_transactions.c.transaction_id == Cashflow.transaction_id,
        )
        .subquery("transaction_ledger_ranked_cashflows")
    )
    cashflow_values = tuple(
        ranked_cashflows.c[column.name]
        for column in Cashflow.__table__.columns
        if column.name != "id"
    )
    return (
        select(
            func.max(ranked_cashflows.c.updated_at).label("selected_cashflow_latest_at"),
            _ordered_jsonb_digest(
                values=cashflow_values,
                order_by=(
                    ranked_cashflows.c.transaction_id.asc(),
                    ranked_cashflows.c.epoch.asc(),
                    ranked_cashflows.c.id.asc(),
                ),
            ).label("selected_cashflow_digest"),
        )
        .where(ranked_cashflows.c.selection_rank == 1)
        .subquery("transaction_ledger_cashflow_evidence")
    )


def _empty_fx_aggregate() -> Any:
    return select(
        cast(literal(None), FxRate.updated_at.type).label("selected_fx_rate_latest_at"),
        cast(literal(None), String).label("selected_fx_rate_digest"),
    ).subquery("transaction_ledger_fx_evidence")


def _selected_fx_rate_aggregate(
    matching_transactions: Any,
    *,
    reporting_currency: str | None,
    as_of_date: date | None,
) -> Any:
    if reporting_currency is None or as_of_date is None:
        return _empty_fx_aggregate()

    source_currencies = union(
        select(matching_transactions.c.currency.label("source_currency")),
        select(matching_transactions.c.trade_currency.label("source_currency")),
    ).cte("transaction_ledger_source_currencies")
    normalized_source_currency = currency_code_sql_expr(source_currencies.c.source_currency)
    normalized_fx_from_currency = currency_code_sql_expr(FxRate.from_currency)
    normalized_fx_to_currency = currency_code_sql_expr(FxRate.to_currency)
    normalized_reporting_currency = reporting_currency.strip().upper()

    ranked_fx_rates = (
        select(
            *FxRate.__table__.columns,
            normalized_fx_from_currency.label("normalized_from_currency"),
            func.row_number()
            .over(
                partition_by=normalized_fx_from_currency,
                order_by=(FxRate.rate_date.desc(), FxRate.id.desc()),
            )
            .label("selection_rank"),
        )
        .join(
            source_currencies,
            normalized_source_currency == normalized_fx_from_currency,
        )
        .where(
            source_currencies.c.source_currency.is_not(None),
            normalized_source_currency != normalized_reporting_currency,
            normalized_fx_to_currency == normalized_reporting_currency,
            FxRate.rate_date <= as_of_date,
        )
        .subquery("transaction_ledger_ranked_fx_rates")
    )
    fx_values = tuple(
        ranked_fx_rates.c[column.name] for column in FxRate.__table__.columns if column.name != "id"
    )
    return (
        select(
            func.max(ranked_fx_rates.c.updated_at).label("selected_fx_rate_latest_at"),
            _ordered_jsonb_digest(
                values=fx_values,
                order_by=(
                    ranked_fx_rates.c.normalized_from_currency.asc(),
                    ranked_fx_rates.c.rate_date.asc(),
                    ranked_fx_rates.c.id.asc(),
                ),
            ).label("selected_fx_rate_digest"),
        )
        .where(ranked_fx_rates.c.selection_rank == 1)
        .subquery("transaction_ledger_fx_evidence")
    )


def transaction_ledger_input_evidence_statement(
    *,
    matching_transactions: Any,
    reporting_currency: str | None,
    as_of_date: date | None,
) -> Any:
    """Build one statement returning fixed-width evidence for the complete filtered scope."""

    transaction_aggregate = _transaction_aggregate(matching_transactions)
    cost_aggregate = _transaction_cost_aggregate(matching_transactions)
    cashflow_aggregate = _selected_cashflow_aggregate(matching_transactions)
    fx_aggregate = _selected_fx_rate_aggregate(
        matching_transactions,
        reporting_currency=reporting_currency,
        as_of_date=as_of_date,
    )
    return (
        select(
            transaction_aggregate.c.transaction_count,
            transaction_aggregate.c.transaction_latest_at,
            transaction_aggregate.c.transaction_digest,
            cost_aggregate.c.transaction_cost_latest_at,
            cost_aggregate.c.transaction_cost_digest,
            cashflow_aggregate.c.selected_cashflow_latest_at,
            cashflow_aggregate.c.selected_cashflow_digest,
            fx_aggregate.c.selected_fx_rate_latest_at,
            fx_aggregate.c.selected_fx_rate_digest,
        )
        .select_from(transaction_aggregate)
        .join(cost_aggregate, true())
        .join(cashflow_aggregate, true())
        .join(fx_aggregate, true())
    )
