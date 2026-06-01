from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any

from ..dtos.transaction_dto import TransactionRecord
from .transaction_reporting_currency import apply_transaction_reporting_currency_fields

ConvertAmount = Callable[
    ...,
    Awaitable[Decimal],
]


async def transaction_records_from_rows(
    *,
    rows: list[Any],
    reporting_currency: str | None,
    as_of_date: date | None,
    convert_amount: ConvertAmount,
) -> list[TransactionRecord]:
    records: list[TransactionRecord] = []
    for row in rows:
        record = transaction_record_from_row(row)
        if reporting_currency and as_of_date is not None:
            await apply_transaction_reporting_currency_fields(
                record=record,
                reporting_currency=reporting_currency,
                as_of_date=as_of_date,
                convert_amount=convert_amount,
            )
        records.append(record)
    return records


def transaction_record_from_row(row: Any) -> TransactionRecord:
    record = TransactionRecord.model_validate(row)
    record.costs = [cost for cost in row.costs or []]
    if row.cashflow:
        record.cashflow = row.cashflow
    return record
