from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.transaction_realized_tax import (
    realized_tax_currency_totals,
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
