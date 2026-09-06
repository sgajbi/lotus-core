"""Verify governed event and booked transaction mapping parity."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.events import TransactionEvent
from pydantic import ValidationError

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    build_fx_processed_transaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping import (  # noqa: E501
    booked_transaction as mapper,
)


def _transaction() -> BookedTransaction:
    return BookedTransaction(
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
        trade_currency="SGD",
        currency="SGD",
        linked_component_ids=("LEG-001", "LEG-002"),
        redemption_price_type="PAR",
        old_factor=Decimal("1"),
        new_factor=Decimal("0.75"),
        principal_proceeds_local=Decimal("255"),
        accrued_interest_proceeds_local=Decimal("5"),
        embedded_fee_amount_local=Decimal("1"),
        embedded_tax_amount_local=Decimal("2"),
    )


def _fx_transaction() -> BookedTransaction:
    return replace(
        _transaction(),
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        settlement_date=datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        component_id="FX-COMP-001",
        linked_component_ids=("FX-BUY-001", "FX-SELL-001"),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        fx_realized_pnl_mode="NONE",
    )


def test_mapper_round_trips_every_event_backed_domain_field() -> None:
    transaction = _transaction()

    event = mapper.to_transaction_event(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert mapper.to_booked_transaction(event) == transaction
    assert event.correlation_id == "corr-001"
    assert event.traceparent == "trace-001"


def test_aware_external_event_maps_to_fx_lineage_without_instant_drift() -> None:
    source = _fx_transaction()
    event = mapper.to_transaction_event(source, correlation_id=None, traceparent=None)

    mapped = mapper.to_booked_transaction(event)
    processed = build_fx_processed_transaction(mapped)

    assert mapped.transaction_date == source.transaction_date
    assert mapped.settlement_date == source.settlement_date
    assert processed.calculation_lineage is not None


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("transaction_date", datetime(2026, 4, 10, 9, 30)),
        ("transaction_date", "2026-04-10T09:30:00"),
        ("settlement_date", datetime(2026, 7, 1, 9, 30)),
        ("settlement_date", "2026-07-01T09:30:00"),
        ("created_at", datetime(2026, 4, 10, 9, 31)),
        ("created_at", "2026-04-10T09:31:00"),
    ],
)
def test_timezone_ambiguous_external_event_cannot_reach_fx_lineage(
    field_name: str,
    value: datetime | str,
) -> None:
    payload = mapper.to_transaction_event(
        _fx_transaction(),
        correlation_id=None,
        traceparent=None,
    ).model_dump()
    payload[field_name] = value

    with pytest.raises(ValidationError, match="timezone-aware") as exc_info:
        TransactionEvent.model_validate(payload)

    assert exc_info.value.errors(include_input=False)[0]["loc"] == (field_name,)


def test_mapper_applies_domain_fields_without_losing_event_envelope() -> None:
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


def test_mapper_keeps_persisted_calculation_lineage_out_of_transport_contract() -> None:
    lineage = build_calculation_lineage(
        algorithm_id="transaction-cost-basis-calculation",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"source_revision": "revision-1"},
        output_payload={"net_cost": Decimal("255")},
    )
    transaction = replace(_transaction(), calculation_lineage=lineage)

    event = mapper.to_transaction_event(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )
    rehydrated = mapper.to_booked_transaction(event)

    assert "calculation_lineage" not in event.model_dump(mode="python")
    assert rehydrated.calculation_lineage is None
    mapper.validate_booked_transaction_event_mapping_contract()


def test_mapper_rejects_external_field_drift() -> None:
    drifted_fields = set(TransactionEvent.model_fields) | {"unsupported_business_field"}

    with pytest.raises(
        mapper.BookedTransactionEventMappingError,
        match="unsupported_business_field",
    ):
        mapper.validate_booked_transaction_event_mapping_contract(drifted_fields)
