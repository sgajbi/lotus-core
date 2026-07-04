from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain_value_objects import CurrencyBasis

from src.services.query_service.app.dtos.transaction_dto import TransactionRecord
from src.services.query_service.app.services.transaction_reporting_currency import (
    apply_transaction_reporting_currency_fields,
    source_currency_for_transaction_field,
)


@pytest.mark.asyncio
async def test_apply_transaction_reporting_currency_fields_converts_money_fields_sequentially() -> (
    None
):
    record = TransactionRecord(
        transaction_id="T1",
        transaction_date=datetime(2025, 1, 10, tzinfo=UTC),
        transaction_type="BUY",
        instrument_id="I1",
        security_id="S1",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        gross_cost=Decimal("1000"),
        trade_fee=Decimal("12.5"),
        trade_currency=" eur ",
        currency=" usd ",
    )
    call_order: list[Decimal] = []
    observed_currency_pairs: list[tuple[str, str]] = []

    async def convert_amount(
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        call_order.append(amount)
        observed_currency_pairs.append((from_currency, to_currency))
        assert to_currency == "SGD"
        assert as_of_date == date(2025, 1, 15)
        return amount * (Decimal("2") if from_currency == "USD" else Decimal("3"))

    await apply_transaction_reporting_currency_fields(
        record=record,
        reporting_currency="SGD",
        as_of_date=date(2025, 1, 15),
        convert_amount=convert_amount,
    )

    assert record.gross_transaction_amount_reporting_currency == Decimal("2000")
    assert record.gross_cost_reporting_currency == Decimal("2000")
    assert record.trade_fee_reporting_currency == Decimal("37.5")
    assert call_order == [Decimal("1000"), Decimal("1000"), Decimal("12.5")]
    assert observed_currency_pairs == [("USD", "SGD"), ("USD", "SGD"), ("EUR", "SGD")]


def test_source_currency_for_transaction_field_prefers_trade_currency_for_trade_basis() -> None:
    record = TransactionRecord(
        transaction_id="T1",
        transaction_date=datetime(2025, 1, 10, tzinfo=UTC),
        transaction_type="BUY",
        instrument_id="I1",
        security_id="S1",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="EUR",
        currency="USD",
    )

    assert (
        source_currency_for_transaction_field(
            record=record,
            currency_basis=CurrencyBasis.TRADE,
        )
        == "EUR"
    )
    assert (
        source_currency_for_transaction_field(
            record=record,
            currency_basis=CurrencyBasis.BOOK,
        )
        == "USD"
    )
