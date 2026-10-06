"""Closed wire metadata is not authority; signed body/identity remain inseparable."""

from copy import deepcopy

import pytest
from portfolio_common.api_contract.async_commands import SourceEvidenceConfirmationInput
from portfolio_common.command_authorization import (
    CommandAuthorizationClaims,
    SignedCommandAuthorization,
)
from portfolio_common.event_contracts import (
    TransactionSourceCorrectionRequestedEvent,
    TransactionSourceEvidenceChangedEvent,
)
from pydantic import ValidationError


def command_payload():
    body = SourceEvidenceConfirmationInput.model_validate(
        {
            "expected_head_id": "raw-7",
            "expected_head_sha256": "a" * 64,
            "reason": "Qualified absent source confirmation",
            "realized_pnl_local": "0",
        }
    )
    claims = CommandAuthorizationClaims(
        issuer="schema-only",
        key_id="schema-only",
        principal="schema-only",
        actor_id="actor",
        tenant_id="tenant",
        command_id="command",
        operation_id="operation",
        target_transaction_id="transaction",
        root_raw_id="raw-7",
        root_raw_sha256="a" * 64,
        expected_head_id=body.expected_head_id,
        expected_head_sha256=body.expected_head_sha256,
        canonical_request_sha256=body.canonical_request_sha256(target_transaction_id="transaction"),
        issued_at=1,
        expires_at=101,
        nonce="nonce",
        correlation_id="correlation",
        trace_id="trace",
    )
    # Schema fixture only: zero signature intentionally confers no cryptographic authority.
    token = SignedCommandAuthorization(claims=claims, signature="0" * 64)
    return {
        "authorization": token.model_dump(mode="json"),
        "body": body.model_dump(mode="json", exclude_unset=True),
        "tenant_id": "tenant",
        "portfolio_id": "portfolio",
        "correlation_id": "correlation",
        "trace_id": "trace",
        "idempotency_key": "command",
        "source_system": "ingestion_service",
        "event_type": "TransactionSourceCorrectionRequested",
        "schema_version": "1.0.0",
    }


def notice_payload():
    return {
        "revision_id": "revision",
        "revision_sha256": "b" * 64,
        "transaction_id": "transaction",
        "portfolio_id": "portfolio",
        "tenant_id": "tenant",
        "operation_id": "operation",
        "root_raw_event_id": 7,
        "correlation_id": "correlation",
        "trace_id": "trace",
        "idempotency_key": "revision",
        "source_system": "persistence_service",
        "event_type": "TransactionSourceEvidenceChanged",
        "schema_version": "1.0.0",
    }


@pytest.mark.parametrize(
    "model,factory",
    [
        (TransactionSourceCorrectionRequestedEvent, command_payload),
        (TransactionSourceEvidenceChangedEvent, notice_payload),
    ],
)
def test_canonical_wire_roundtrip_and_unknown_fields_refuse(model, factory):
    payload = factory()
    event = model.model_validate(payload)
    assert model.model_validate_json(event.model_dump_json(exclude_unset=True)) == event
    assert model.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        model.model_validate(payload | {"economic_booking": True})


@pytest.mark.parametrize(
    "model,factory",
    [
        (TransactionSourceCorrectionRequestedEvent, command_payload),
        (TransactionSourceEvidenceChangedEvent, notice_payload),
    ],
)
@pytest.mark.parametrize(
    "field", ["event_type", "schema_version", "source_system", "trace_id", "idempotency_key"]
)
def test_required_metadata_is_not_synthesized(model, factory, field):
    payload = factory()
    del payload[field]
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "2.0.0"),
        ("source_system", "caller"),
        ("event_type", "TransactionIngested"),
        ("tenant_id", "foreign"),
        ("correlation_id", "foreign"),
        ("trace_id", "foreign"),
        ("idempotency_key", "foreign"),
        ("traceparent", "invalid"),
    ],
)
def test_command_metadata_and_signed_bindings_refuse(field, value):
    with pytest.raises(ValidationError):
        TransactionSourceCorrectionRequestedEvent.model_validate(command_payload() | {field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_head_id", "foreign"),
        ("expected_head_sha256", "b" * 64),
        ("reason", "Changed reason"),
        ("realized_pnl_local", "1"),
        ("realized_pnl_local", None),
        ("realized_pnl_local", False),
    ],
)
def test_command_body_changes_cannot_retain_attestation(field, value):
    payload = deepcopy(command_payload())
    payload["body"][field] = value
    with pytest.raises(ValidationError):
        TransactionSourceCorrectionRequestedEvent.model_validate(payload)


def test_unchecked_copy_is_revalidated_at_wire_boundary():
    event = TransactionSourceCorrectionRequestedEvent.model_validate(command_payload())
    copied = event.model_copy(update={"idempotency_key": "foreign"})
    with pytest.raises(ValidationError):
        TransactionSourceCorrectionRequestedEvent.model_validate(
            copied.model_dump(exclude_unset=True)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "2.0.0"),
        ("source_system", "caller"),
        ("event_type", "TransactionIngested"),
        ("idempotency_key", "foreign"),
        ("root_raw_event_id", True),
        ("root_raw_event_id", 0),
        ("revision_sha256", "not-a-hash"),
        ("traceparent", "invalid"),
    ],
)
def test_notice_is_closed_reload_identity_not_qualification(field, value):
    with pytest.raises(ValidationError):
        TransactionSourceEvidenceChangedEvent.model_validate(notice_payload() | {field: value})
