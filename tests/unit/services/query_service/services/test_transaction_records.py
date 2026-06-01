from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import Cashflow, Transaction, TransactionCost

from src.services.query_service.app.dtos.transaction_dto import TransactionRecord
from src.services.query_service.app.services.transaction_records import (
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
