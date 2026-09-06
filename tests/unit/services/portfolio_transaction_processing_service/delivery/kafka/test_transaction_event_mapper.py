"""Tests for the Kafka transaction-event anti-corruption mapper."""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.events import GOVERNED_EVENT_ENVELOPE_FIELDS, TransactionEvent

from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    transaction_event_mapper as mapper,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BOOKED_TRANSACTION_DERIVED_FIELDS,
)


def _transaction_event() -> TransactionEvent:
    return TransactionEvent(
        event_type="RawTransactionPersisted",
        schema_version="1.0.0",
        correlation_id="corr-source",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        transaction_id="TX-001",
        portfolio_id="PB-001",
        tenant_id="tenant-test",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="sgd",
        currency="sgd",
        linked_component_ids=["COMP-1", "COMP-2"],
        dependency_reference_ids=["DEP-1"],
        allocated_cost_basis_local=Decimal("50"),
        allocated_cost_basis_base=Decimal("55"),
        redemption_price_type="PAR",
        old_factor=Decimal("1"),
        new_factor=Decimal("0.75"),
        principal_proceeds_local=Decimal("255"),
        accrued_interest_proceeds_local=Decimal("5"),
        embedded_fee_amount_local=Decimal("1"),
        embedded_tax_amount_local=Decimal("2"),
        epoch=7,
    )


def test_domain_model_covers_every_transaction_business_field() -> None:
    domain_fields = {
        field.name
        for field in fields(BookedTransaction)
        if field.name not in BOOKED_TRANSACTION_DERIVED_FIELDS
    }
    event_business_fields = set(TransactionEvent.model_fields) - GOVERNED_EVENT_ENVELOPE_FIELDS

    assert domain_fields == event_business_fields
    assert BOOKED_TRANSACTION_DERIVED_FIELDS == {
        "calculation_lineage",
        "lot_restatement",
        "source_lot_order_quantity",
        "source_lot_original_quantity",
    }
    mapper.validate_transaction_event_mapping_contract()


def test_mapper_creates_immutable_domain_command_and_round_trips_event() -> None:
    event = _transaction_event()

    command = mapper.map_transaction_event(event, event_id="transactions.persisted-0-42")

    assert command.transaction.transaction_id == "TX-001"
    assert command.transaction.trade_currency == "SGD"
    assert command.transaction.linked_component_ids == ("COMP-1", "COMP-2")
    assert command.transaction.new_factor == Decimal("0.75")
    assert command.transaction.principal_proceeds_local == Decimal("255")
    assert command.metadata.event_id == "transactions.persisted-0-42"
    assert command.metadata.correlation_id == "corr-source"
    with pytest.raises(FrozenInstanceError):
        command.transaction.transaction_id = "changed"
    assert mapper.to_transaction_event(command).model_dump(mode="python") == event.model_dump(
        mode="python"
    )


def test_mapper_uses_resolved_correlation_id_without_mutating_source_event() -> None:
    event = _transaction_event()

    command = mapper.map_transaction_event(
        event,
        event_id="transactions.persisted-0-42",
        correlation_id="corr-resolved",
        repair_delivery_id="repair-command-001",
    )

    assert command.metadata.correlation_id == "corr-resolved"
    assert command.metadata.repair_delivery_id == "repair-command-001"
    assert event.correlation_id == "corr-source"


def test_mapping_contract_fails_fast_on_external_field_drift() -> None:
    drifted_fields = [*TransactionEvent.model_fields, "new_economic_field"]

    with pytest.raises(mapper.TransactionEventMappingError, match="new_economic_field"):
        mapper.validate_transaction_event_mapping_contract(drifted_fields)
