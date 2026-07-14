"""Apply deterministic effective-dated FX rates to cost-basis engine inputs."""

from bisect import bisect_right
from datetime import date, datetime
from typing import Any

from ...ports import CostBasisFxRatePort


class FxRateNotFoundError(Exception):
    """Report that no effective FX rate exists on or before a transaction date."""


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
        rate_dates = [fx_rate.effective_date for fx_rate in rate_window]
        for transaction, effective_date in pair_transactions:
            effective_rate_index = bisect_right(rate_dates, effective_date) - 1
            if effective_rate_index < 0:
                raise FxRateNotFoundError(
                    f"FX rate for {trade_currency}->{base_currency} on "
                    f"{transaction['transaction_date']} not found. Retrying..."
                )
            transaction["transaction_fx_rate"] = rate_window[effective_rate_index].rate

    return transactions
