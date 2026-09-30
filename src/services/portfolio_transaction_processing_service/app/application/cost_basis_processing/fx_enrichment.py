"""Apply deterministic effective-dated FX rates to cost-basis engine inputs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ...domain.transaction.fx_rate_origin import REFERENCE_DERIVED_FX_RATE_ORIGIN
from ...ports import CostBasisFxRatePort
from ..errors import FxRateNotFoundError, TransactionProcessingRejected
from ..fx_rate_selection import select_latest_effective_fx_rate


def _normalized_currency(value: object) -> str:
    return str(value or "").strip().upper()


def _transaction_effective_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


async def enrich_cost_basis_transactions_with_fx(
    *,
    transactions: list[dict[str, Any]],
    portfolio_base_currency: str,
    fx_rates: CostBasisFxRatePort,
) -> list[dict[str, Any]]:
    """Attach latest-on-or-before FX rates using one bounded read per currency pair."""

    normalized_base_currency = _normalized_currency(portfolio_base_currency)
    transactions_by_pair: dict[
        tuple[str, str],
        list[tuple[dict[str, Any], date]],
    ] = {}
    for transaction in transactions:
        trade_currency = _normalized_currency(transaction.get("trade_currency"))
        transaction["trade_currency"] = trade_currency
        transaction["portfolio_base_currency"] = normalized_base_currency

        if trade_currency == normalized_base_currency:
            supplied_rate = transaction.get("transaction_fx_rate")
            if supplied_rate is not None and Decimal(supplied_rate) != Decimal(1):
                raise TransactionProcessingRejected(
                    reason_code="same_currency_fx_rate_invalid",
                    detail={
                        "transaction_id": transaction.get("transaction_id"),
                        "currency": trade_currency,
                        "transaction_fx_rate": str(supplied_rate),
                    },
                    retryable=False,
                )
            transaction["transaction_fx_rate"] = Decimal(1)
            if supplied_rate is None:
                transaction["transaction_fx_rate_origin"] = REFERENCE_DERIVED_FX_RATE_ORIGIN
            continue

        if transaction.get("transaction_fx_rate") is not None:
            continue

        effective_date = _transaction_effective_date(transaction["transaction_date"])
        transactions_by_pair.setdefault((trade_currency, normalized_base_currency), []).append(
            (transaction, effective_date)
        )

    for (trade_currency, base_currency), pair_transactions in transactions_by_pair.items():
        requested_dates = [effective_date for _, effective_date in pair_transactions]
        rate_window = await fx_rates.get_fx_rate_window(
            from_currency=trade_currency,
            to_currency=base_currency,
            start_date=min(requested_dates),
            end_date=max(requested_dates),
        )
        for transaction, effective_date in pair_transactions:
            effective_rate = select_latest_effective_fx_rate(rate_window, effective_date)
            if effective_rate is None:
                raise FxRateNotFoundError(
                    f"FX rate for {trade_currency}->{base_currency} on "
                    f"{transaction['transaction_date']} not found. Retrying..."
                )
            transaction["transaction_fx_rate"] = effective_rate.rate
            transaction["transaction_fx_rate_origin"] = REFERENCE_DERIVED_FX_RATE_ORIGIN

    return transactions
