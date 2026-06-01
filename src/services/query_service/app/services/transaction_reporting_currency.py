from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import cast

from ..dtos.transaction_dto import TransactionRecord

ConvertAmount = Callable[..., Awaitable[Decimal]]

TRANSACTION_REPORTING_CURRENCY_FIELDS = (
    ("gross_transaction_amount", "gross_transaction_amount_reporting_currency", "book"),
    ("gross_cost", "gross_cost_reporting_currency", "book"),
    ("trade_fee", "trade_fee_reporting_currency", "trade"),
    ("net_cost", "net_cost_reporting_currency", "book"),
    ("realized_gain_loss", "realized_gain_loss_reporting_currency", "book"),
    (
        "realized_capital_pnl_local",
        "realized_capital_pnl_local_reporting_currency",
        "trade",
    ),
    ("realized_fx_pnl_local", "realized_fx_pnl_local_reporting_currency", "trade"),
    ("realized_total_pnl_local", "realized_total_pnl_local_reporting_currency", "trade"),
    ("withholding_tax_amount", "withholding_tax_amount_reporting_currency", "book"),
    (
        "other_interest_deductions_amount",
        "other_interest_deductions_amount_reporting_currency",
        "book",
    ),
    ("net_interest_amount", "net_interest_amount_reporting_currency", "book"),
)


async def apply_transaction_reporting_currency_fields(
    *,
    record: TransactionRecord,
    reporting_currency: str,
    as_of_date: date,
    convert_amount: ConvertAmount,
) -> None:
    for source_field, target_field, currency_basis in TRANSACTION_REPORTING_CURRENCY_FIELDS:
        amount = getattr(record, source_field)
        if amount is None:
            continue
        converted_value = await convert_amount(
            amount=amount,
            from_currency=source_currency_for_transaction_field(
                record=record,
                currency_basis=currency_basis,
            ),
            to_currency=reporting_currency,
            as_of_date=as_of_date,
        )
        setattr(record, target_field, converted_value)


def source_currency_for_transaction_field(
    *,
    record: TransactionRecord,
    currency_basis: str,
) -> str:
    if currency_basis == "trade" and record.trade_currency:
        return cast(str, record.trade_currency)
    return cast(str, record.currency)
