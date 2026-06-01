from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..dtos.transaction_dto import RealizedTaxCurrencyTotal
from ..repositories.currency_codes import normalize_currency_code

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
