from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.dtos.transaction_dto import RealizedTaxCurrencyTotal
from src.services.query_service.app.services.transaction_realized_tax import (
    realized_tax_currency_totals,
    realized_tax_reporting_currency_total,
)


def test_realized_tax_currency_totals_groups_normalized_currency_buckets() -> None:
    totals = realized_tax_currency_totals(
        [
            SimpleNamespace(
                currency=" usd ",
                withholding_tax_amount=Decimal("10"),
                other_interest_deductions_amount=Decimal("5"),
            ),
            SimpleNamespace(
                currency="USD",
                withholding_tax_amount=Decimal("2"),
                other_interest_deductions_amount=Decimal("3"),
            ),
            SimpleNamespace(
                currency="EUR",
                withholding_tax_amount=Decimal("7"),
                other_interest_deductions_amount=None,
            ),
        ]
    )

    assert [total.currency for total in totals] == ["EUR", "USD"]
    assert totals[0].transaction_count == 1
    assert totals[0].withholding_tax_amount == Decimal("7")
    assert totals[0].other_tax_deductions_amount == Decimal("0")
    assert totals[0].total_tax_amount == Decimal("7")
    assert totals[1].transaction_count == 2
    assert totals[1].withholding_tax_amount == Decimal("12")
    assert totals[1].other_tax_deductions_amount == Decimal("8")
    assert totals[1].total_tax_amount == Decimal("20")


def test_realized_tax_currency_totals_returns_empty_list_for_empty_evidence() -> None:
    assert realized_tax_currency_totals([]) == []


@pytest.mark.asyncio
async def test_realized_tax_reporting_currency_total_converts_totals_sequentially() -> None:
    call_order: list[str] = []

    async def convert_amount(
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        call_order.append(from_currency)
        assert to_currency == "SGD"
        assert as_of_date == date(2025, 1, 15)
        return amount

    total = await realized_tax_reporting_currency_total(
        currency_totals=[
            RealizedTaxCurrencyTotal(
                currency="EUR",
                transaction_count=1,
                withholding_tax_amount=Decimal("7"),
                other_tax_deductions_amount=Decimal("0"),
                total_tax_amount=Decimal("7"),
            ),
            RealizedTaxCurrencyTotal(
                currency="USD",
                transaction_count=1,
                withholding_tax_amount=Decimal("5"),
                other_tax_deductions_amount=Decimal("0"),
                total_tax_amount=Decimal("5"),
            ),
        ],
        reporting_currency="SGD",
        as_of_date=date(2025, 1, 15),
        convert_amount=convert_amount,
    )

    assert total == Decimal("12")
    assert call_order == ["EUR", "USD"]


@pytest.mark.asyncio
async def test_realized_tax_reporting_currency_total_skips_without_reporting_currency() -> None:
    async def convert_amount(**_: object) -> Decimal:
        raise AssertionError("conversion should not be called")

    assert (
        await realized_tax_reporting_currency_total(
            currency_totals=[],
            reporting_currency=None,
            as_of_date=date(2025, 1, 15),
            convert_amount=convert_amount,
        )
        is None
    )
