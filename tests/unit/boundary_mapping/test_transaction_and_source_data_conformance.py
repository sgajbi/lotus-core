from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from portfolio_common.event_publisher import KafkaEventPublisher
from portfolio_common.events import TransactionEvent
from portfolio_common.logging_utils import correlation_id_var
from pydantic import BaseModel, ValidationError

from services.ingestion_service.app.DTOs.transaction_dto import Transaction
from services.ingestion_service.app.services.ingestion_event_payloads import (
    transaction_event_payload,
)
from services.ingestion_service.app.services.ingestion_service import IngestionService
from src.services.persistence_service.app.adapters.event_record_mapper import (
    transaction_event_to_record_values,
)
from src.services.persistence_service.app.adapters.persistence_event_adapter import (
    decode_persistence_message_payload,
    validate_persistence_event_payload,
)
from src.services.query_service.app.dtos.reference_integration_dto import ReferencePageMetadata
from src.services.query_service.app.dtos.reference_integration_portfolio_tax_lot_dto import (
    PortfolioTaxLotWindowResponse,
    PortfolioTaxLotWindowSupportability,
)
from src.services.query_service.app.read_models import (
    PerformanceEconomicsCostReadRecord,
    PerformanceEconomicsTransactionReadRecord,
    PortfolioTaxLotReadRecord,
)
from src.services.query_service.app.services.performance_component_economics import (
    build_performance_component_economics_rows,
)
from src.services.query_service.app.services.reference_data_mappers import portfolio_tax_lot_record


class _CapturingProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish_message(
        self,
        *,
        topic: str,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]] | None = None,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
                "headers": headers or [],
            }
        )


def _kafka_json_round_trip(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, default=_json_default))


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {value!r}")


def _mock_kafka_message(payload: dict[str, Any]) -> MagicMock:
    msg = MagicMock()
    msg.topic.return_value = "transactions.raw.received"
    msg.partition.return_value = 2
    msg.offset.return_value = 41
    msg.value.return_value = json.dumps(payload, default=_json_default).encode("utf-8")
    return msg


@pytest.mark.asyncio
async def test_transaction_mapping_chain_preserves_event_and_record_invariants() -> None:
    producer = _CapturingProducer()
    service = IngestionService(KafkaEventPublisher(producer))  # type: ignore[arg-type]
    correlation_token = correlation_id_var.set("corr-boundary-001")
    transaction = Transaction(
        transaction_id="TXN-MAP-001",
        portfolio_id="PORT-MAP-001",
        instrument_id="EQ_US_AAPL",
        security_id="EQ_US_AAPL",
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
        economic_event_id="EVT-TXN-MAP-001",
        linked_transaction_group_id="LTG-TXN-MAP-001",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        source_system="OMS_PRIMARY",
    )

    try:
        await service.publish_transaction(
            transaction,
            idempotency_key="idem-boundary-001",
        )
    finally:
        correlation_id_var.reset(correlation_token)

    published = producer.messages[0]
    decoded_headers = {name: value.decode("utf-8") for name, value in published["headers"]}
    assert published["key"] == "PORT-MAP-001"
    assert decoded_headers == {
        "correlation_id": "corr-boundary-001",
        "idempotency_key": "idem-boundary-001",
    }
    assert published["value"] == transaction_event_payload(transaction)

    event_payload = _kafka_json_round_trip(
        {
            **published["value"],
            "event_type": "transaction.raw.received",
            "schema_version": "transaction.raw.v1",
            "correlation_id": "corr-boundary-001",
        }
    )
    event = TransactionEvent.model_validate(event_payload)
    record_values = transaction_event_to_record_values(event)

    assert event.event_type == "transaction.raw.received"
    assert event.schema_version == "transaction.raw.v1"
    assert event.correlation_id == "corr-boundary-001"
    assert event.transaction_type == "BUY"
    assert event.transaction_date == datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    assert event.settlement_date == datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
    assert event.trade_currency == "USD"
    assert event.currency == "USD"
    assert event.trade_fee == Decimal("5.0000000000")
    assert event.quantity == Decimal("100.0000000000")
    assert event.price == Decimal("150.0550000000")

    assert record_values["transaction_id"] == "TXN-MAP-001"
    assert record_values["portfolio_id"] == "PORT-MAP-001"
    assert record_values["trade_fee"] == Decimal("5.0000000000")
    assert record_values["source_system"] == "OMS_PRIMARY"
    assert record_values["calculation_policy_id"] == "BUY_DEFAULT_POLICY"
    assert record_values["calculation_policy_version"] == "1.0.0"
    assert "event_type" not in record_values
    assert "schema_version" not in record_values
    assert "correlation_id" not in record_values
    assert "brokerage" not in record_values


def test_transaction_event_mapping_rejects_unknown_and_missing_fields() -> None:
    payload = {
        "transaction_id": "TXN-MAP-002",
        "portfolio_id": "PORT-MAP-001",
        "instrument_id": "EQ_US_AAPL",
        "security_id": "EQ_US_AAPL",
        "transaction_date": "2026-03-25T09:30:00+00:00",
        "transaction_type": "BUY",
        "quantity": "100.0000000000",
        "price": "150.0550000000",
        "gross_transaction_amount": "15005.5000000000",
        "trade_currency": "USD",
        "currency": "USD",
    }

    with pytest.raises(ValidationError) as unknown_field_error:
        TransactionEvent.model_validate({**payload, "unexpected_transport_field": "reject"})
    assert any(
        error["loc"] == ("unexpected_transport_field",)
        for error in unknown_field_error.value.errors()
    )

    missing_identifier_payload = dict(payload)
    missing_identifier_payload.pop("transaction_id")
    with pytest.raises(ValidationError) as missing_field_error:
        TransactionEvent.model_validate(missing_identifier_payload)
    assert any(error["loc"] == ("transaction_id",) for error in missing_field_error.value.errors())


def test_persistence_message_adapter_preserves_event_identity_and_lineage() -> None:
    payload = {
        "transaction_id": "TXN-MAP-003",
        "portfolio_id": "PORT-MAP-001",
        "instrument_id": "EQ_US_AAPL",
        "security_id": "EQ_US_AAPL",
        "transaction_date": "2026-03-25T09:30:00+00:00",
        "transaction_type": "BUY",
        "quantity": "100.0000000000",
        "price": "150.0550000000",
        "gross_transaction_amount": "15005.5000000000",
        "trade_currency": "USD",
        "currency": "USD",
        "correlation_id": "corr-boundary-003",
    }

    decoded = decode_persistence_message_payload(_mock_kafka_message(payload))
    envelope = validate_persistence_event_payload(decoded, TransactionEvent)

    assert decoded.event_id == "transactions.raw.received-2-41"
    assert decoded.fallback_correlation_id == "corr-boundary-003"
    assert envelope.event_id == "transactions.raw.received-2-41"
    assert envelope.idempotency_key == "TXN-MAP-003"
    assert envelope.portfolio_id == "PORT-MAP-001"
    assert envelope.event.transaction_id == "TXN-MAP-003"
    assert envelope.event.correlation_id == "corr-boundary-003"


def test_persistence_message_adapter_uses_event_id_for_non_transaction_events() -> None:
    class MinimalPersistenceEvent(BaseModel):
        schema_version: str

    decoded = decode_persistence_message_payload(
        _mock_kafka_message({"schema_version": "minimal.v1"})
    )
    envelope = validate_persistence_event_payload(decoded, MinimalPersistenceEvent)

    assert envelope.idempotency_key == "transactions.raw.received-2-41"
    assert envelope.portfolio_id == "N/A"


def test_source_data_tax_lot_mapping_preserves_lineage_and_envelope_identity() -> None:
    lot = portfolio_tax_lot_record(
        PortfolioTaxLotReadRecord(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            security_id=" eq_us_aapl ",
            instrument_id=" EQ_US_AAPL ",
            lot_id="LOT-TXN-BUY-AAPL-001",
            open_quantity="100.0000000000",
            original_quantity="150.0000000000",
            acquisition_date=date(2026, 3, 25),
            lot_cost_base="15005.5000000000",
            lot_cost_local="15005.5000000000",
            source_transaction_id="TXN-MAP-001",
            source_system="OMS_PRIMARY",
            calculation_policy_id="BUY_DEFAULT_POLICY",
            calculation_policy_version="1.0.0",
            local_currency="USD",
            updated_at=datetime(2026, 3, 31, 8, 0, tzinfo=UTC),
        )
    )

    response = PortfolioTaxLotWindowResponse(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=date(2026, 3, 31),
        generated_at=datetime(2026, 3, 31, 8, 0, tzinfo=UTC),
        lots=[lot],
        page=ReferencePageMetadata(
            page_size=250,
            sort_key="acquisition_date:asc,lot_id:asc",
            returned_component_count=1,
            request_scope_fingerprint="taxlot-window-map-001",
            next_page_token=None,
        ),
        supportability=PortfolioTaxLotWindowSupportability(
            state="READY",
            reason="TAX_LOTS_READY",
            requested_security_count=1,
            returned_lot_count=1,
            missing_security_ids=[],
        ),
        lineage={
            "source_system": "position_lot_state",
            "contract_version": "rfc_087_v1",
        },
    )

    assert response.product_name == "PortfolioTaxLotWindow"
    assert response.product_version == "v1"
    assert response.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.as_of_date == date(2026, 3, 31)
    assert response.generated_at == datetime(2026, 3, 31, 8, 0, tzinfo=UTC)
    assert response.page.returned_component_count == 1
    assert response.supportability.state == "READY"
    assert response.lineage["contract_version"] == "rfc_087_v1"
    assert response.lots[0].security_id == "eq_us_aapl"
    assert response.lots[0].instrument_id == "EQ_US_AAPL"
    assert response.lots[0].open_quantity == Decimal("100.0000000000")
    assert response.lots[0].cost_basis_base == Decimal("15005.5000000000")
    assert response.lots[0].local_currency == "USD"
    assert response.lots[0].source_lineage == {
        "source_system": "OMS_PRIMARY",
        "source_transaction_id": "TXN-MAP-001",
        "calculation_policy_id": "BUY_DEFAULT_POLICY",
        "calculation_policy_version": "1.0.0",
    }


def test_performance_economics_mapping_uses_typed_read_records_for_optional_joins() -> None:
    rows = build_performance_component_economics_rows(
        [
            PerformanceEconomicsTransactionReadRecord(
                transaction_id="TXN-MAP-PERF-001",
                portfolio_id="PB_SG_GLOBAL_BAL_001",
                security_id=" EQ_US_AAPL ",
                transaction_type=" dividend ",
                currency=" eur ",
                trade_currency=" usd ",
                transaction_date=datetime(2026, 3, 25, 9, 30, tzinfo=UTC),
                gross_transaction_amount=Decimal("1000.0000000000"),
                trade_fee=Decimal("1.0000000000"),
                withholding_tax_amount=Decimal("15.0000000000"),
                other_interest_deductions_amount=Decimal("5.0000000000"),
                net_interest_amount=Decimal("80.0000000000"),
                realized_capital_pnl_local=Decimal("0"),
                realized_fx_pnl_local=Decimal("0"),
                realized_total_pnl_local=Decimal("0"),
                realized_capital_pnl_base=Decimal("10.0000000000"),
                realized_fx_pnl_base=Decimal("2.0000000000"),
                realized_total_pnl_base=Decimal("12.0000000000"),
                transaction_fx_rate=Decimal("1.1000000000"),
                fx_contract_id="FXC-MAP-001",
                cashflow=None,
                costs=(
                    PerformanceEconomicsCostReadRecord(
                        fee_type="brokerage",
                        amount=Decimal("1.2500000000"),
                        currency="usd",
                        updated_at=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
                    ),
                    PerformanceEconomicsCostReadRecord(
                        fee_type="exchange_fee",
                        amount=Decimal("2.5000000000"),
                        currency="eur",
                        updated_at=datetime(2026, 3, 25, 10, 5, tzinfo=UTC),
                    ),
                ),
                updated_at=datetime(2026, 3, 25, 9, 45, tzinfo=UTC),
            )
        ]
    )

    assert rows[0].security_id == "EQ_US_AAPL"
    assert rows[0].transaction_type == "DIVIDEND"
    assert rows[0].currency == "EUR"
    assert rows[0].trade_currency == "USD"
    assert rows[0].cashflow_amount is None
    assert rows[0].trade_fee_currency == "MIXED"
    assert [(fee.currency, fee.amount) for fee in rows[0].trade_fee_components] == [
        ("EUR", Decimal("2.5000000000")),
        ("USD", Decimal("1.2500000000")),
    ]
    assert rows[0].source_lineage == {
        "source_system": "transactions",
        "source_table": "transactions,cashflows,transaction_costs",
        "contract_version": "performance_component_economics_v1",
    }
