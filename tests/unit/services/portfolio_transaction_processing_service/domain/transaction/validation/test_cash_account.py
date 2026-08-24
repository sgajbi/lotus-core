"""Prove registry-driven cash-account instrument eligibility."""

import pytest
from portfolio_common.domain.transaction.type_registry import TRANSACTION_TYPE_REGISTRY

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    CashAccountRequiredValidationError,
    CashAccountRequiredValidationReasonCode,
    assert_cash_account_required_instrument,
)


@pytest.mark.parametrize(
    "transaction_type",
    [
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.settlement_behavior == "cash_account_required"
    ],
)
def test_every_registry_cash_account_type_accepts_authoritative_cash_metadata(
    transaction_type: str,
) -> None:
    assert_cash_account_required_instrument(
        transaction_type,
        instrument_reference_available=True,
        product_type=" cash ",
        asset_class=None,
    )


@pytest.mark.parametrize("transaction_type", ["DEPOSIT", "WITHDRAWAL", "FEE", "TAX"])
def test_public_cash_account_types_reject_non_cash_authority(transaction_type: str) -> None:
    with pytest.raises(CashAccountRequiredValidationError) as raised:
        assert_cash_account_required_instrument(
            transaction_type,
            instrument_reference_available=True,
            product_type="EQUITY",
            asset_class="EQUITY",
        )

    assert raised.value.reason_code is CashAccountRequiredValidationReasonCode.NON_CASH_INSTRUMENT
    assert raised.value.transaction_type == transaction_type


@pytest.mark.parametrize("instrument_reference_available", [False, True])
def test_cash_account_type_rejects_missing_classification_authority(
    instrument_reference_available: bool,
) -> None:
    with pytest.raises(CashAccountRequiredValidationError) as raised:
        assert_cash_account_required_instrument(
            "FEE",
            instrument_reference_available=instrument_reference_available,
            product_type=None,
            asset_class=None,
        )

    assert raised.value.reason_code is (
        CashAccountRequiredValidationReasonCode.INSTRUMENT_AUTHORITY_UNAVAILABLE
    )


def test_cash_identifier_prefix_cannot_override_non_cash_authority() -> None:
    with pytest.raises(CashAccountRequiredValidationError) as raised:
        assert_cash_account_required_instrument(
            "FEE",
            instrument_reference_available=True,
            product_type="CASH_USD",
            asset_class="CASH_ACCOUNT_001",
        )

    assert raised.value.reason_code is CashAccountRequiredValidationReasonCode.NON_CASH_INSTRUMENT


def test_non_cash_account_transaction_does_not_require_cash_classification() -> None:
    assert_cash_account_required_instrument(
        "BUY",
        instrument_reference_available=True,
        product_type="EQUITY",
        asset_class="EQUITY",
    )
