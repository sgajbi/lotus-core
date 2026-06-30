from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import Cashflow, Transaction, TransactionCost
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN

from src.services.query_service.app.dtos.transaction_dto import TransactionRecord
from src.services.query_service.app.services.transaction_records import (
    paginated_transaction_ledger_response,
    transaction_record_from_row,
    transaction_records_from_rows,
)

pytestmark = pytest.mark.asyncio


async def test_transaction_record_from_row_preserves_costs_and_cashflow() -> None:
    row = Transaction(
        transaction_id="T-CASHFLOW",
        transaction_date=datetime(2025, 1, 10),
        transaction_type="DEPOSIT",
        instrument_id="CASH",
        security_id="CASH",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("5000"),
        currency="USD",
        costs=[
            TransactionCost(
                transaction_id="T-CASHFLOW",
                fee_type="BROKERAGE",
                amount=Decimal("2.50"),
                currency="USD",
            )
        ],
        cashflow=Cashflow(
            amount=Decimal("5000"),
            currency="USD",
            classification="CASHFLOW_IN",
            timing="BOD",
            calculation_type="NET",
            is_position_flow=True,
            is_portfolio_flow=True,
        ),
    )

    record = transaction_record_from_row(row)

    assert isinstance(record, TransactionRecord)
    assert record.transaction_id == "T-CASHFLOW"
    assert len(record.costs) == 1
    assert record.costs[0].fee_type == "BROKERAGE"
    assert record.cashflow is not None
    assert record.cashflow.amount == Decimal("5000")
    assert record.cashflow.is_portfolio_flow is True


async def test_transaction_records_from_rows_applies_reporting_currency_in_row_order() -> None:
    rows = [
        Transaction(
            transaction_id="T1",
            transaction_date=datetime(2025, 1, 10),
            transaction_type="BUY",
            instrument_id="I1",
            security_id="S1",
            quantity=Decimal("10"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000"),
            currency="USD",
        ),
        Transaction(
            transaction_id="T2",
            transaction_date=datetime(2025, 1, 11),
            transaction_type="SELL",
            instrument_id="I2",
            security_id="S2",
            quantity=Decimal("5"),
            price=Decimal("50"),
            gross_transaction_amount=Decimal("250"),
            currency="EUR",
        ),
    ]
    call_order: list[str] = []
    convert_amount = AsyncMock(return_value=Decimal("1"))

    async def apply_reporting_currency_fields(
        *,
        record: TransactionRecord,
        reporting_currency: str,
        as_of_date: date,
        convert_amount: object,
    ) -> None:
        call_order.append(record.transaction_id)
        assert reporting_currency == "SGD"
        assert as_of_date == date(2025, 1, 15)
        assert convert_amount is expected_convert_amount

    expected_convert_amount = convert_amount
    with patch(
        "src.services.query_service.app.services.transaction_records.apply_transaction_reporting_currency_fields",
        new_callable=AsyncMock,
    ) as apply_transaction_reporting_currency_fields:
        apply_transaction_reporting_currency_fields.side_effect = apply_reporting_currency_fields

        records = await transaction_records_from_rows(
            rows=rows,
            reporting_currency="SGD",
            as_of_date=date(2025, 1, 15),
            convert_amount=convert_amount,
        )

    assert [record.transaction_id for record in records] == ["T1", "T2"]
    assert call_order == ["T1", "T2"]
    assert apply_transaction_reporting_currency_fields.await_count == 2


async def test_transaction_records_from_rows_skips_reporting_currency_without_context() -> None:
    row = Transaction(
        transaction_id="T1",
        transaction_date=datetime(2025, 1, 10),
        transaction_type="BUY",
        instrument_id="I1",
        security_id="S1",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        currency="USD",
    )

    with patch(
        "src.services.query_service.app.services.transaction_records.apply_transaction_reporting_currency_fields",
        new_callable=AsyncMock,
    ) as apply_transaction_reporting_currency_fields:
        records = await transaction_records_from_rows(
            rows=[row],
            reporting_currency="SGD",
            as_of_date=None,
            convert_amount=AsyncMock(),
        )

    assert [record.transaction_id for record in records] == ["T1"]
    apply_transaction_reporting_currency_fields.assert_not_awaited()


def _transaction_record(transaction_id: str) -> TransactionRecord:
    return TransactionRecord(
        transaction_id=transaction_id,
        transaction_date=datetime(2025, 1, 10),
        transaction_type="BUY",
        instrument_id="I1",
        security_id="S1",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        currency="USD",
    )


async def test_paginated_transaction_ledger_response_marks_complete_window() -> None:
    latest_evidence_timestamp = datetime(2025, 1, 16, 9, 30, tzinfo=UTC)

    response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency="SGD",
        total_count=2,
        skip=0,
        limit=10,
        transactions=[_transaction_record("T1"), _transaction_record("T2")],
        effective_as_of_date=date(2025, 1, 15),
        end_date=date(2025, 1, 31),
        latest_evidence_timestamp=latest_evidence_timestamp,
    )

    assert response.product_name == "TransactionLedgerWindow"
    assert response.product_version == "v1"
    assert response.portfolio_id == "P1"
    assert response.reporting_currency == "SGD"
    assert response.total == 2
    assert response.skip == 0
    assert response.limit == 10
    assert [transaction.transaction_id for transaction in response.transactions] == ["T1", "T2"]
    assert response.as_of_date == date(2025, 1, 15)
    assert response.data_quality_status == COMPLETE
    assert response.latest_evidence_timestamp == latest_evidence_timestamp
    assert response.reason_codes == ["TRANSACTION_LEDGER_READY"]
    assert response.missing_instrument_reference_count == 0
    assert response.missing_instrument_security_ids == []


async def test_paginated_transaction_ledger_response_marks_partial_window() -> None:
    response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=25,
        skip=10,
        limit=10,
        transactions=[_transaction_record("T11")],
        effective_as_of_date=date(2025, 1, 15),
        end_date=None,
        latest_evidence_timestamp=None,
    )

    assert response.data_quality_status == PARTIAL
    assert response.as_of_date == date(2025, 1, 15)
    assert response.reason_codes == ["TRANSACTION_LEDGER_PAGE_PARTIAL"]


async def test_transaction_ledger_response_marks_missing_instrument_reference_partial() -> None:
    response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=2,
        skip=0,
        limit=10,
        transactions=[_transaction_record("T1"), _transaction_record("T2")],
        effective_as_of_date=date(2025, 1, 15),
        end_date=None,
        latest_evidence_timestamp=None,
        missing_instrument_security_ids=["S2"],
    )

    assert response.data_quality_status == PARTIAL
    assert response.reason_codes == ["TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING"]
    assert response.missing_instrument_reference_count == 1
    assert response.missing_instrument_security_ids == ["S2"]


async def test_paginated_transaction_ledger_response_uses_end_date_then_today_fallback() -> None:
    end_date_response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=0,
        skip=0,
        limit=10,
        transactions=[],
        effective_as_of_date=None,
        end_date=date(2025, 1, 31),
        latest_evidence_timestamp=None,
        today=lambda: date(2025, 2, 1),
    )
    today_response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=0,
        skip=0,
        limit=10,
        transactions=[],
        effective_as_of_date=None,
        end_date=None,
        latest_evidence_timestamp=None,
        today=lambda: date(2025, 2, 1),
    )

    assert end_date_response.as_of_date == date(2025, 1, 31)
    assert today_response.as_of_date == date(2025, 2, 1)
    assert end_date_response.data_quality_status == UNKNOWN
    assert today_response.data_quality_status == UNKNOWN
    assert end_date_response.reason_codes == ["TRANSACTION_LEDGER_EMPTY"]
    assert today_response.reason_codes == ["TRANSACTION_LEDGER_EMPTY"]
