from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.events import TransactionEvent

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    legacy_transaction_event_mapper as mapper,
)


def _transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
        linked_component_ids=("LEG-001", "LEG-002"),
    )


def test_legacy_mapper_round_trips_every_domain_field() -> None:
    transaction = _transaction()

    event = mapper.to_transaction_event(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert mapper.to_booked_transaction(event) == transaction
    assert event.correlation_id == "corr-001"
    assert event.traceparent == "trace-001"


def test_legacy_mapper_applies_domain_fields_without_losing_event_envelope() -> None:
    transaction = _transaction()
    event = mapper.to_transaction_event(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )
    enriched = replace(
        transaction,
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
        calculation_policy_id="POLICY-001",
        calculation_policy_version="2.0.0",
    )

    updated_event = mapper.with_booked_transaction_fields(event, enriched)

    assert updated_event.correlation_id == event.correlation_id
    assert updated_event.traceparent == event.traceparent
    assert mapper.to_booked_transaction(updated_event) == enriched
    assert mapper.to_booked_transaction(event) == transaction


def test_legacy_mapper_rejects_external_field_drift() -> None:
    drifted_fields = set(TransactionEvent.model_fields) | {"unsupported_business_field"}

    with pytest.raises(
        mapper.LegacyTransactionEventMappingError,
        match="unsupported_business_field",
    ):
        mapper.validate_legacy_transaction_event_mapping_contract(drifted_fields)
