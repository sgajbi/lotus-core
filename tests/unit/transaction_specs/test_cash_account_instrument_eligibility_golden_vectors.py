"""Verify the cash-account authority boundary against governed golden vectors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    CashAccountRequiredValidationError,
    assert_cash_account_required_instrument,
)

_VECTOR_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "transaction_economics"
    / "cash_account_instrument_eligibility.v1.json"
)
_VECTOR_PACK: dict[str, Any] = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))


def test_cash_account_eligibility_pack_declares_authority_policy() -> None:
    assert _VECTOR_PACK["pack_id"] == "cash-account-instrument-eligibility"
    assert _VECTOR_PACK["pack_version"] == "1.0.0"
    assert _VECTOR_PACK["policy"] == {
        "authority": "server-owned-instrument-metadata",
        "identifier_inference_allowed": False,
    }
    assert len(_VECTOR_PACK["vectors"]) == 6
    assert all(vector["rationale"] for vector in _VECTOR_PACK["vectors"])


@pytest.mark.parametrize(
    "vector",
    _VECTOR_PACK["vectors"],
    ids=lambda vector: vector["vector_id"],
)
def test_cash_account_eligibility_matches_golden_vector(vector: dict[str, Any]) -> None:
    expected_reason_code = vector["expected_reason_code"]

    if expected_reason_code is None:
        assert_cash_account_required_instrument(
            vector["transaction_type"],
            instrument_reference_available=vector["instrument_reference_available"],
            product_type=vector["product_type"],
            asset_class=vector["asset_class"],
        )
        return

    with pytest.raises(CashAccountRequiredValidationError) as raised:
        assert_cash_account_required_instrument(
            vector["transaction_type"],
            instrument_reference_available=vector["instrument_reference_available"],
            product_type=vector["product_type"],
            asset_class=vector["asset_class"],
        )

    assert raised.value.reason_code.value == expected_reason_code
