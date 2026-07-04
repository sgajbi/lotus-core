from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import cast

from portfolio_common.domain_value_objects import CurrencyBasis, CurrencyCode, MoneyAmount

from ..dtos.transaction_dto import TransactionRecord

ConvertAmount = Callable[..., Awaitable[Decimal]]

TRANSACTION_REPORTING_CURRENCY_FIELDS = (
    ("gross_transaction_amount", "gross_transaction_amount_reporting_currency", CurrencyBasis.BOOK),
    ("gross_cost", "gross_cost_reporting_currency", CurrencyBasis.BOOK),
    ("trade_fee", "trade_fee_reporting_currency", CurrencyBasis.TRADE),
    ("net_cost", "net_cost_reporting_currency", CurrencyBasis.BOOK),
    ("realized_gain_loss", "realized_gain_loss_reporting_currency", CurrencyBasis.BOOK),
    (
        "realized_capital_pnl_local",
        "realized_capital_pnl_local_reporting_currency",
        CurrencyBasis.TRADE,
    ),
    ("realized_fx_pnl_local", "realized_fx_pnl_local_reporting_currency", CurrencyBasis.TRADE),
    (
        "realized_total_pnl_local",
        "realized_total_pnl_local_reporting_currency",
        CurrencyBasis.TRADE,
    ),
    ("withholding_tax_amount", "withholding_tax_amount_reporting_currency", CurrencyBasis.BOOK),
    (
        "other_interest_deductions_amount",
        "other_interest_deductions_amount_reporting_currency",
        CurrencyBasis.BOOK,
    ),
    ("net_interest_amount", "net_interest_amount_reporting_currency", CurrencyBasis.BOOK),
)


async def apply_transaction_reporting_currency_fields(
    *,
    record: TransactionRecord,
    reporting_currency: str,
    as_of_date: date,
    convert_amount: ConvertAmount,
) -> None:
    target_currency = CurrencyCode.from_raw(reporting_currency)
    for source_field, target_field, currency_basis in TRANSACTION_REPORTING_CURRENCY_FIELDS:
        amount = getattr(record, source_field)
        money = MoneyAmount.optional_from_raw(
            amount=amount,
            currency=source_currency_for_transaction_field(
                record=record,
                currency_basis=currency_basis,
            ),
        )
        if money is None:
            continue
        converted_value = await convert_amount(
            amount=money.amount,
            from_currency=money.currency.value,
            to_currency=target_currency.value,
            as_of_date=as_of_date,
        )
        setattr(record, target_field, converted_value)


def source_currency_for_transaction_field(
    *,
    record: TransactionRecord,
    currency_basis: CurrencyBasis,
) -> str:
    if currency_basis == CurrencyBasis.TRADE and record.trade_currency:
        return CurrencyCode.from_raw(cast(str, record.trade_currency)).value
    return CurrencyCode.from_raw(cast(str, record.currency)).value
