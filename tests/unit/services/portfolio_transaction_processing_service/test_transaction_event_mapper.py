from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.events import GOVERNED_EVENT_ENVELOPE_FIELDS, TransactionEvent

from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    transaction_event_mapper as mapper,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction


def _transaction_event() -> TransactionEvent:
    return TransactionEvent(
        event_type="RawTransactionPersisted",
        schema_version="1.0.0",
        correlation_id="corr-source",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        transaction_id="TX-001",
        portfolio_id="PB-001",
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
        epoch=7,
    )


def test_domain_model_covers_every_transaction_business_field() -> None:
    domain_fields = {field.name for field in fields(BookedTransaction)}
    event_business_fields = set(TransactionEvent.model_fields) - GOVERNED_EVENT_ENVELOPE_FIELDS

    assert domain_fields == event_business_fields
    mapper.validate_transaction_event_mapping_contract()


def test_mapper_creates_immutable_domain_command_and_round_trips_event() -> None:
    event = _transaction_event()

    command = mapper.map_transaction_event(event, event_id="transactions.persisted-0-42")

    assert command.transaction.transaction_id == "TX-001"
    assert command.transaction.trade_currency == "SGD"
    assert command.transaction.linked_component_ids == ("COMP-1", "COMP-2")
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
    )

    assert command.metadata.correlation_id == "corr-resolved"
    assert event.correlation_id == "corr-source"


def test_mapping_contract_fails_fast_on_external_field_drift() -> None:
    drifted_fields = [*TransactionEvent.model_fields, "new_economic_field"]

    with pytest.raises(mapper.TransactionEventMappingError, match="new_economic_field"):
        mapper.validate_transaction_event_mapping_contract(drifted_fields)
