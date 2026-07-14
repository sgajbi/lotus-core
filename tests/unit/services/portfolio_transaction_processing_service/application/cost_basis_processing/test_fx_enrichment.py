"""Verify bounded effective-dated FX enrichment for cost-basis inputs."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, call

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    EffectiveFxRate,
)
from src.services.portfolio_transaction_processing_service.app.ports import CostBasisFxRatePort


@pytest.mark.asyncio
async def test_same_currency_is_normalized_without_lookup() -> None:
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    transactions = [
        {
            "transaction_id": "BUY_PADDED_CCY_01",
            "transaction_date": "2025-12-05T10:00:00Z",
            "trade_currency": " usd ",
        }
    ]

    enriched = await cost_basis_processing.enrich_cost_basis_transactions_with_fx(
        transactions=transactions,
        portfolio_base_currency=" USD ",
        fx_rates=fx_rates,
    )

    fx_rates.get_fx_rate_window.assert_not_awaited()
    assert enriched[0]["trade_currency"] == "USD"
    assert enriched[0]["portfolio_base_currency"] == "USD"
    assert "transaction_fx_rate" not in enriched[0]


@pytest.mark.asyncio
async def test_effective_dated_history_is_batched_by_currency_pair() -> None:
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(effective_date=date(2026, 4, 1), rate=Decimal("1.40")),
        EffectiveFxRate(effective_date=date(2026, 4, 10), rate=Decimal("1.45")),
    ]
    transaction_dates = ("05", "10", "15") * 100
    transactions = [
        {
            "transaction_id": f"EUR-{index:03d}",
            "transaction_date": f"2026-04-{day}T10:00:00Z",
            "trade_currency": " eur " if index == 0 else "EUR",
        }
        for index, day in enumerate(transaction_dates)
    ]

    enriched = await cost_basis_processing.enrich_cost_basis_transactions_with_fx(
        transactions=transactions,
        portfolio_base_currency="SGD",
        fx_rates=fx_rates,
    )

    fx_rates.get_fx_rate_window.assert_awaited_once_with(
        from_currency="EUR",
        to_currency="SGD",
        start_date=date(2026, 4, 5),
        end_date=date(2026, 4, 15),
    )
    assert len(enriched) == 300
    assert [transaction["transaction_fx_rate"] for transaction in enriched] == [
        Decimal("1.40") if day == "05" else Decimal("1.45") for day in transaction_dates
    ]


@pytest.mark.asyncio
async def test_each_distinct_currency_pair_uses_one_bounded_window_read() -> None:
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.side_effect = [
        [EffectiveFxRate(effective_date=date(2026, 4, 1), rate=Decimal("1.40"))],
        [EffectiveFxRate(effective_date=date(2026, 4, 2), rate=Decimal("1.75"))],
    ]
    transactions = [
        {
            "transaction_id": "EUR-001",
            "transaction_date": "2026-04-05T10:00:00Z",
            "trade_currency": "EUR",
        },
        {
            "transaction_id": "EUR-002",
            "transaction_date": "2026-04-06T10:00:00Z",
            "trade_currency": "EUR",
        },
        {
            "transaction_id": "GBP-001",
            "transaction_date": "2026-04-07T10:00:00Z",
            "trade_currency": "GBP",
        },
    ]

    enriched = await cost_basis_processing.enrich_cost_basis_transactions_with_fx(
        transactions=transactions,
        portfolio_base_currency="SGD",
        fx_rates=fx_rates,
    )

    assert fx_rates.get_fx_rate_window.await_args_list == [
        call(
            from_currency="EUR",
            to_currency="SGD",
            start_date=date(2026, 4, 5),
            end_date=date(2026, 4, 6),
        ),
        call(
            from_currency="GBP",
            to_currency="SGD",
            start_date=date(2026, 4, 7),
            end_date=date(2026, 4, 7),
        ),
    ]
    assert [transaction["transaction_fx_rate"] for transaction in enriched] == [
        Decimal("1.40"),
        Decimal("1.40"),
        Decimal("1.75"),
    ]


@pytest.mark.asyncio
async def test_transaction_before_first_available_rate_is_rejected() -> None:
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(effective_date=date(2026, 4, 10), rate=Decimal("1.45"))
    ]

    with pytest.raises(cost_basis_processing.FxRateNotFoundError, match="EUR->SGD"):
        await cost_basis_processing.enrich_cost_basis_transactions_with_fx(
            transactions=[
                {
                    "transaction_id": "EUR-BEFORE-FIRST-RATE",
                    "transaction_date": "2026-04-05T10:00:00Z",
                    "trade_currency": "EUR",
                }
            ],
            portfolio_base_currency="SGD",
            fx_rates=fx_rates,
        )
