"""Supplier provenance must not silently change booking identity or invent a source batch."""

import hashlib
import json

import pytest
from portfolio_common.domain.transaction.payload_identity import transaction_payload_fingerprint
from portfolio_common.event_mapping import (
    DecodedKafkaEventPayload,
    EventContractValidationError,
    validate_kafka_event_payload,
)
from portfolio_common.events import PortfolioEvent, TransactionEvent
from portfolio_common.transaction_batch_lineage import (
    TransactionBatchLineage,
    transaction_batch_lineage_from_payload,
)
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.transaction_dto import (
    Transaction,
    TransactionIngestionRequest,
)


def _payload():
    return {
        "transaction_id": "TX-LINEAGE-001",
        "portfolio_id": "PORT-LINEAGE-001",
        "instrument_id": "SEC-LINEAGE-001",
        "security_id": "SEC-LINEAGE-001",
        "transaction_date": "2026-10-09T09:00:00Z",
        "transaction_type": "BUY",
        "quantity": "2",
        "price": "10",
        "gross_transaction_amount": "20",
        "trade_currency": "USD",
        "currency": "USD",
        "source_system": "CUSTODY",
    }


@pytest.mark.parametrize("model", [Transaction, TransactionEvent])
@pytest.mark.parametrize(
    "change",
    [
        {"source_record_id": "RECORD-1", "source_system": None},
        {"source_batch_id": " "},
        {"source_record_id": " RECORD-1"},
        {"source_batch_identifer": "BATCH-1"},
        {"observed_at": "2026-10-09T09:30:00"},
    ],
)
def test_invalid_lineage_is_rejected_at_ingress_and_event_boundary(model, change):
    with pytest.raises(ValidationError):
        model.model_validate({**_payload(), **change})


def test_supplier_lineage_round_trip_preserves_reference_and_economic_identity():
    legacy = Transaction.model_validate(_payload())
    current = Transaction.model_validate(
        {
            **_payload(),
            "source_record_id": "RECORD-1",
            "source_batch_id": "BATCH-1",
            "observed_at": "2026-10-09T17:30:00+08:00",
            "source_transaction_reference": "CORPORATE-ACTION-CHILD-1",
        }
    )
    event = TransactionEvent.model_validate(current.model_dump())
    assert event.source_record_id == "RECORD-1"
    assert event.source_transaction_reference == "CORPORATE-ACTION-CHILD-1"
    assert event.observed_at.isoformat() == "2026-10-09T17:30:00+08:00"
    assert legacy.source_batch_id is None
    assert not {"source_record_id", "source_batch_id", "observed_at"}.intersection(
        legacy.model_dump()
    )
    original = event.model_copy(
        update={"source_record_id": None, "source_batch_id": None, "observed_at": None}
    )
    assert transaction_payload_fingerprint(event.model_dump()) == transaction_payload_fingerprint(
        original.model_dump()
    )


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_transaction_governed_boundary_accepts_declared_compatible_versions(version):
    event = validate_kafka_event_payload(
        DecodedKafkaEventPayload(
            "event-1",
            {**_payload(), "event_type": "TransactionIngested", "schema_version": version},
        ),
        TransactionEvent,
        expected_event_type="TransactionIngested",
    )
    assert event.schema_version == version


def test_batch_identity_uses_supplier_scope_not_content_or_membership():
    original = {"transactions": [{**_payload(), "source_batch_id": "BATCH-1"}]}
    first = transaction_batch_lineage_from_payload(original)
    changed = transaction_batch_lineage_from_payload(
        {
            "transactions": [
                {**_payload(), "source_batch_id": "BATCH-1", "quantity": "99"},
                {**_payload(), "source_batch_id": "BATCH-1", "transaction_id": "TX-LINEAGE-002"},
            ]
        }
    )
    assert first.reason == changed.reason == "PROVEN"
    assert first.fingerprint(tenant_id="tenant-a") == changed.fingerprint(tenant_id="tenant-a")
    assert first.fingerprint(tenant_id="tenant-a") != first.fingerprint(tenant_id="tenant-b")


@pytest.mark.parametrize(
    ("records", "reason"),
    [
        ([], "EMPTY_WINDOW"),
        ([{}], "LEGACY_UNKNOWN"),
        ([{"source_system": "CUSTODY", "source_batch_id": "BATCH-1"}, {}], "LEGACY_UNKNOWN"),
        (
            [
                {"source_system": "CUSTODY", "source_batch_id": "BATCH-1"},
                {"source_system": "CUSTODY", "source_batch_id": "BATCH-2"},
            ],
            "MIXED_BATCHES",
        ),
    ],
)
def test_unproven_batch_is_explicit_and_never_fingerprinted(records, reason):
    evidence = transaction_batch_lineage_from_payload({"transactions": records})
    assert evidence.reason == reason
    assert evidence.fingerprint(tenant_id="tenant-a") is None
    assert evidence.source_batch_id is None
    assert evidence.lineage()["batch_lineage_status"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "fields",
    [
        {"reason": "PROVEN"},
        {"reason": "PROVEN", "source_system": " CUSTODY", "source_batch_id": "BATCH-1"},
        {"reason": "LEGACY_UNKNOWN", "source_system": "CUSTODY", "source_batch_id": "BATCH-1"},
    ],
)
def test_retained_batch_projection_refuses_contradictory_assertions(fields):
    with pytest.raises(ValidationError):
        TransactionBatchLineage.model_validate(fields)


def test_legacy_validated_request_bytes_match_pre_lineage_main():
    # Produced independently from exact pre-change main a571ebd972550c52c72bbeb6ac48c1be87477ff6.
    # Explicit receipt time controls the pre-existing default_factory, not request contents.
    request = TransactionIngestionRequest.model_validate(
        {
            "transactions": [
                {**_payload(), "created_at": "2026-10-09T09:31:00Z"},
            ]
        }
    )
    canonical = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert hashlib.sha256(canonical.encode()).hexdigest() == (
        "c7f31ec54f37286d1a9d45cfb773490b92af9ebbde1b89358524592abfaa0b37"
    )


@pytest.mark.parametrize(
    ("model", "event_type", "version"),
    [
        (TransactionEvent, "TransactionIngested", "2.0.0"),
        (TransactionEvent, "TransactionIngested", None),
        (PortfolioEvent, "PortfolioIngested", "1.1.0"),
    ],
)
def test_governed_transport_rejects_missing_or_unrelated_versions(model, event_type, version):
    with pytest.raises(EventContractValidationError):
        validate_kafka_event_payload(
            DecodedKafkaEventPayload(
                "event-1", {"event_type": event_type, "schema_version": version}
            ),
            model,
            expected_event_type=event_type,
        )
