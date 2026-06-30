from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..dtos.transaction_dto import PaginatedTransactionResponse, TransactionRecord
from .transaction_metadata import ledger_data_quality_status, ledger_reason_codes
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


def paginated_transaction_ledger_response(
    *,
    portfolio_id: str,
    reporting_currency: str | None,
    total_count: int,
    skip: int,
    limit: int,
    transactions: list[TransactionRecord],
    effective_as_of_date: date | None,
    end_date: date | None,
    latest_evidence_timestamp: datetime | None,
    missing_instrument_security_ids: list[str] | None = None,
    today: Callable[[], date] = date.today,
) -> PaginatedTransactionResponse:
    missing_instrument_security_ids = missing_instrument_security_ids or []
    return PaginatedTransactionResponse(
        portfolio_id=portfolio_id,
        reporting_currency=reporting_currency,
        total=total_count,
        skip=skip,
        limit=limit,
        transactions=transactions,
        **source_data_product_runtime_metadata(
            as_of_date=effective_as_of_date or end_date or today(),
            data_quality_status=ledger_data_quality_status(
                total_count=total_count,
                returned_count=len(transactions),
                skip=skip,
                missing_instrument_security_ids=missing_instrument_security_ids,
            ),
            latest_evidence_timestamp=latest_evidence_timestamp,
        ),
        reason_codes=ledger_reason_codes(
            total_count=total_count,
            returned_count=len(transactions),
            skip=skip,
            missing_instrument_security_ids=missing_instrument_security_ids,
        ),
        missing_instrument_reference_count=len(missing_instrument_security_ids),
        missing_instrument_security_ids=missing_instrument_security_ids,
    )
