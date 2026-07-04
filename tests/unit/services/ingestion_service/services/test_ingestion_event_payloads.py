from datetime import UTC, date, datetime
from decimal import Decimal

from src.services.ingestion_service.app.DTOs.business_date_dto import BusinessDate
from src.services.ingestion_service.app.DTOs.fx_rate_dto import FxRate
from src.services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.ingestion_service.app.services.ingestion_event_payloads import (
    business_date_event_payload,
    fx_rate_event_payload,
    transaction_event_payload,
)


def test_transaction_event_payload_preserves_boundary_types_and_lineage() -> None:
    transaction = Transaction(
        transaction_id=" TXN-PAYLOAD-001 ",
        portfolio_id=" PORT-PAYLOAD-001 ",
        instrument_id=" EQ_US_AAPL ",
        security_id=" EQ_US_AAPL ",
        transaction_date=datetime(2026, 3, 25, 9, 30, tzinfo=UTC),
        settlement_date=datetime(2026, 3, 27, 0, 0, tzinfo=UTC),
        transaction_type=" buy ",
        quantity=Decimal("100.0000000000"),
        price=Decimal("150.0550000000"),
        gross_transaction_amount=Decimal("15005.5000000000"),
        trade_currency=" usd ",
        currency=" usd ",
        brokerage=Decimal("2.5000000000"),
        stamp_duty=Decimal("1.2000000000"),
        exchange_fee=Decimal("0.7000000000"),
        gst=Decimal("0.4500000000"),
        other_fees=Decimal("0.1500000000"),
        economic_event_id="EVT-PAYLOAD-001",
        linked_transaction_group_id="LTG-PAYLOAD-001",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        source_system="OMS_PRIMARY",
    )

    payload = transaction_event_payload(transaction)

    assert payload["transaction_id"] == "TXN-PAYLOAD-001"
    assert payload["portfolio_id"] == "PORT-PAYLOAD-001"
    assert payload["transaction_type"] == "BUY"
    assert payload["transaction_date"] == datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    assert payload["settlement_date"] == datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
    assert payload["trade_currency"] == "USD"
    assert payload["currency"] == "USD"
    assert payload["quantity"] == Decimal("100.0000000000")
    assert payload["price"] == Decimal("150.0550000000")
    assert payload["trade_fee"] == Decimal("5.0000000000")
    assert payload["source_system"] == "OMS_PRIMARY"
    assert payload["calculation_policy_id"] == "BUY_DEFAULT_POLICY"
    assert payload["calculation_policy_version"] == "1.0.0"


def test_reference_event_payloads_preserve_dates_decimals_and_source_fields() -> None:
    business_date = BusinessDate(
        business_date=date(2026, 3, 25),
        calendar_code="GLOBAL",
        market_code="XSWX",
        source_system="CALENDAR_MASTER",
        source_batch_id="bd-20260325",
    )
    fx_rate = FxRate(
        from_currency=" usd ",
        to_currency=" sgd ",
        rate_date=date(2026, 3, 25),
        rate=Decimal("1.3500000000"),
    )

    business_date_payload = business_date_event_payload(business_date)
    fx_rate_payload = fx_rate_event_payload(fx_rate)

    assert business_date_payload == {
        "business_date": date(2026, 3, 25),
        "calendar_code": "GLOBAL",
        "market_code": "XSWX",
        "source_system": "CALENDAR_MASTER",
        "source_batch_id": "bd-20260325",
    }
    assert fx_rate_payload == {
        "from_currency": "USD",
        "to_currency": "SGD",
        "rate_date": date(2026, 3, 25),
        "rate": Decimal("1.3500000000"),
    }
