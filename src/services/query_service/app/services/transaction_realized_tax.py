from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..dtos.transaction_dto import (
    PortfolioRealizedTaxSummaryResponse,
    RealizedTaxCurrencyTotal,
)
from ..repositories.currency_codes import normalize_currency_code
from .transaction_metadata import ledger_data_quality_status

ConvertAmount = Callable[..., Awaitable[Decimal]]


@dataclass
class RealizedTaxAccumulator:
    transaction_count: int = 0
    withholding_tax_amount: Decimal = Decimal("0")
    other_tax_deductions_amount: Decimal = Decimal("0")


def realized_tax_currency_totals(
    transactions: list[object],
) -> list[RealizedTaxCurrencyTotal]:
    totals: dict[str, RealizedTaxAccumulator] = {}
    for transaction in transactions:
        currency = normalize_currency_code(str(getattr(transaction, "currency")))
        bucket = totals.setdefault(currency, RealizedTaxAccumulator())
        withholding_tax = getattr(transaction, "withholding_tax_amount") or Decimal("0")
        other_deductions = getattr(transaction, "other_interest_deductions_amount") or Decimal("0")
        bucket.transaction_count += 1
        bucket.withholding_tax_amount += withholding_tax
        bucket.other_tax_deductions_amount += other_deductions

    return [
        RealizedTaxCurrencyTotal(
            currency=currency,
            transaction_count=bucket.transaction_count,
            withholding_tax_amount=bucket.withholding_tax_amount,
            other_tax_deductions_amount=bucket.other_tax_deductions_amount,
            total_tax_amount=bucket.withholding_tax_amount + bucket.other_tax_deductions_amount,
        )
        for currency, bucket in sorted(totals.items())
    ]


async def realized_tax_reporting_currency_total(
    *,
    currency_totals: list[RealizedTaxCurrencyTotal],
    reporting_currency: str | None,
    as_of_date: date,
    convert_amount: ConvertAmount,
) -> Decimal | None:
    if reporting_currency is None:
        return None

    converted_currency_totals = []
    for total in currency_totals:
        converted_currency_totals.append(
            await convert_amount(
                amount=total.total_tax_amount,
                from_currency=total.currency,
                to_currency=reporting_currency,
                as_of_date=as_of_date,
            )
        )
    return sum(converted_currency_totals, Decimal("0"))


def portfolio_realized_tax_summary_response(
    *,
    portfolio_id: str,
    base_currency: str,
    reporting_currency: str | None,
    start_date: date | None,
    end_date: date | None,
    as_of_date: date,
    source_transaction_count: int,
    currency_totals: list[RealizedTaxCurrencyTotal],
    reporting_currency_total_tax_amount: Decimal | None,
    latest_evidence_timestamp: object,
) -> PortfolioRealizedTaxSummaryResponse:
    return PortfolioRealizedTaxSummaryResponse(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        reporting_currency=reporting_currency,
        start_date=start_date,
        end_date=end_date,
        source_transaction_count=source_transaction_count,
        tax_evidence_transaction_count=sum(total.transaction_count for total in currency_totals),
        currency_totals=currency_totals,
        reporting_currency_total_tax_amount=reporting_currency_total_tax_amount,
        reason_codes=[
            "PORTFOLIO_REALIZED_TAX_SUMMARY_READY"
            if currency_totals
            else "PORTFOLIO_REALIZED_TAX_EVIDENCE_EMPTY"
        ],
        **source_data_product_runtime_metadata(
            as_of_date=as_of_date,
            data_quality_status=ledger_data_quality_status(
                total_count=source_transaction_count,
                returned_count=source_transaction_count,
                skip=0,
            ),
            latest_evidence_timestamp=latest_evidence_timestamp,
        ),
    )
