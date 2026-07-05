from datetime import UTC, datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent

from src.services.pipeline_orchestrator_service.app.adapters.outbox_event_mapper import (
    pipeline_outbox_event_payload,
)


def test_pipeline_outbox_event_payload_preserves_governed_event_metadata() -> None:
    event = TransactionEvent(
        event_type="ProcessedTransactionPersisted",
        schema_version="transaction.processed.v1",
        correlation_id="corr-pipeline-001",
        transaction_id="TXN-PIPE-MAP-001",
        portfolio_id="PORT-PIPE-001",
        instrument_id="INST-PIPE-001",
        security_id="SEC-PIPE-001",
        transaction_date=datetime(2026, 3, 7, 10, 15, tzinfo=UTC),
        transaction_type="BUY",
        quantity=Decimal("10.5000"),
        price=Decimal("99.1250"),
        gross_transaction_amount=Decimal("1040.8125"),
        trade_currency="USD",
        currency="USD",
        epoch=4,
    )

    payload = pipeline_outbox_event_payload(event)

    assert payload["event_type"] == "ProcessedTransactionPersisted"
    assert payload["schema_version"] == "transaction.processed.v1"
    assert payload["correlation_id"] == "corr-pipeline-001"
    assert payload["transaction_date"] == "2026-03-07T10:15:00Z"
    assert payload["quantity"] == "10.5000"
    assert payload["price"] == "99.1250"
    assert payload["gross_transaction_amount"] == "1040.8125"
