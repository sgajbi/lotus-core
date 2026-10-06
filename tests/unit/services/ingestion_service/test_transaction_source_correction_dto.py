"""Source confirmation preserves caller presence without accepting caller authority."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.transaction_source_correction_dto import (
    TransactionSourceCorrectionRequest,
)


def payload(**changes):
    return {
        "expected_head_id": "raw-root",
        "expected_head_sha256": "1" * 64,
        "reason": "Confirmed absent local FX source as zero",
        "realized_pnl_local": "0",
        **changes,
    }


def test_request_preserves_exact_supplied_basis_and_decimal_value():
    request = TransactionSourceCorrectionRequest.model_validate(payload())
    assert request.realized_pnl_local == Decimal("0")
    assert request.realized_pnl_base is None
    assert request.supplied_bases == ("local",)
    assert request.model_fields_set == {
        "expected_head_id",
        "expected_head_sha256",
        "reason",
        "realized_pnl_local",
    }


@pytest.mark.parametrize("value", [None, True, 0, 0.0, "NaN", "Infinity", ""])
def test_supplied_source_rejects_null_or_lossy_numeric_input(value):
    with pytest.raises(ValidationError):
        TransactionSourceCorrectionRequest.model_validate(payload(realized_pnl_local=value))


@pytest.mark.parametrize("field", ["tenant_id", "actor_id", "portfolio_id", "authorized_scope"])
def test_caller_scope_and_authority_fields_are_forbidden(field):
    with pytest.raises(ValidationError):
        TransactionSourceCorrectionRequest.model_validate(payload(**{field: "caller-asserted"}))


def test_empty_confirmation_and_blank_reason_are_invalid():
    empty = payload()
    del empty["realized_pnl_local"]
    with pytest.raises(ValidationError):
        TransactionSourceCorrectionRequest.model_validate(empty)
    with pytest.raises(ValidationError):
        TransactionSourceCorrectionRequest.model_validate(payload(reason=" "))


def test_digest_preserves_presence_target_revision_and_reason_not_decimal_spelling():
    original = TransactionSourceCorrectionRequest.model_validate(payload())
    same = TransactionSourceCorrectionRequest.model_validate(payload(realized_pnl_local="0.00"))
    both = TransactionSourceCorrectionRequest.model_validate(payload(realized_pnl_base="0"))
    new_head = TransactionSourceCorrectionRequest.model_validate(
        payload(expected_head_id="revision")
    )
    new_reason = TransactionSourceCorrectionRequest.model_validate(
        payload(reason="Verified correction")
    )
    digest = original.canonical_request_sha256(target_transaction_id="transaction")
    assert digest == same.canonical_request_sha256(target_transaction_id="transaction")
    for changed in (both, new_head, new_reason):
        assert digest != changed.canonical_request_sha256(target_transaction_id="transaction")
    assert digest != original.canonical_request_sha256(target_transaction_id="other")


def test_signed_companion_amount_is_not_normalized_to_zero():
    request = TransactionSourceCorrectionRequest.model_validate(payload(realized_pnl_base="-12.00"))
    assert request.realized_pnl_base == Decimal("-12")
    assert request.supplied_bases == ("local", "base")
