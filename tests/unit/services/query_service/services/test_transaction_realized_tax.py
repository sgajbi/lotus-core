from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from portfolio_common.reconciliation_quality import COMPLETE, UNKNOWN

from src.services.query_service.app.dtos.transaction_dto import RealizedTaxCurrencyTotal
from src.services.query_service.app.services.transaction_realized_tax import (
    portfolio_realized_tax_summary_response,
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


def test_portfolio_realized_tax_summary_response_marks_ready_with_runtime_metadata() -> None:
    latest_evidence_timestamp = datetime(2025, 1, 16, 9, 30, tzinfo=UTC)

    response = portfolio_realized_tax_summary_response(
        portfolio_id="P1",
        base_currency="USD",
        reporting_currency="SGD",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        as_of_date=date(2025, 1, 15),
        source_transaction_count=3,
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
                transaction_count=2,
                withholding_tax_amount=Decimal("12"),
                other_tax_deductions_amount=Decimal("8"),
                total_tax_amount=Decimal("20"),
            ),
        ],
        reporting_currency_total_tax_amount=Decimal("27"),
        latest_evidence_timestamp=latest_evidence_timestamp,
    )

    assert response.product_name == "PortfolioRealizedTaxSummary"
    assert response.product_version == "v1"
    assert response.portfolio_id == "P1"
    assert response.base_currency == "USD"
    assert response.reporting_currency == "SGD"
    assert response.source_transaction_count == 3
    assert response.tax_evidence_transaction_count == 3
    assert response.reporting_currency_total_tax_amount == Decimal("27")
    assert response.reason_codes == ["PORTFOLIO_REALIZED_TAX_SUMMARY_READY"]
    assert response.as_of_date == date(2025, 1, 15)
    assert response.data_quality_status == COMPLETE
    assert response.latest_evidence_timestamp == latest_evidence_timestamp


def test_portfolio_realized_tax_summary_response_marks_empty_evidence_unknown() -> None:
    response = portfolio_realized_tax_summary_response(
        portfolio_id="P1",
        base_currency="USD",
        reporting_currency=None,
        start_date=None,
        end_date=None,
        as_of_date=date(2025, 1, 15),
        source_transaction_count=0,
        currency_totals=[],
        reporting_currency_total_tax_amount=None,
        latest_evidence_timestamp=None,
    )

    assert response.source_transaction_count == 0
    assert response.tax_evidence_transaction_count == 0
    assert response.currency_totals == []
    assert response.reporting_currency_total_tax_amount is None
    assert response.reason_codes == ["PORTFOLIO_REALIZED_TAX_EVIDENCE_EMPTY"]
    assert response.data_quality_status == UNKNOWN
    assert response.latest_evidence_timestamp is None
