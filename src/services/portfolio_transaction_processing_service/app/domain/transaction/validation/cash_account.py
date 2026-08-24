"""Validate registry-owned cash-account instrument eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from portfolio_common.domain.transaction.type_registry import (
    get_transaction_type_definition,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..cash_instrument import is_cash_instrument


class CashAccountRequiredValidationReasonCode(StrEnum):
    """Identify stable cash-account instrument eligibility failures."""

    INSTRUMENT_AUTHORITY_UNAVAILABLE = "CASH_ACCOUNT_001_INSTRUMENT_AUTHORITY_UNAVAILABLE"
    NON_CASH_INSTRUMENT = "CASH_ACCOUNT_002_NON_CASH_INSTRUMENT"


@dataclass(frozen=True, slots=True)
class CashAccountRequiredValidationError(ValueError):
    """Report a booking that cannot satisfy its registry settlement contract."""

    reason_code: CashAccountRequiredValidationReasonCode
    transaction_type: str
    field: str
    message: str

    def __str__(self) -> str:
        return self.message


def assert_cash_account_required_instrument(
    transaction_type: str,
    *,
    instrument_reference_available: bool,
    product_type: object = None,
    asset_class: object = None,
) -> None:
    """Fail closed when a cash-account-required booking lacks cash authority."""

    normalized_type = str(normalize_transaction_control_code(transaction_type))
    definition = get_transaction_type_definition(normalized_type)
    if definition is None or definition.settlement_behavior != "cash_account_required":
        return
    if not instrument_reference_available or not _has_instrument_classification(
        product_type=product_type,
        asset_class=asset_class,
    ):
        raise CashAccountRequiredValidationError(
            reason_code=(CashAccountRequiredValidationReasonCode.INSTRUMENT_AUTHORITY_UNAVAILABLE),
            transaction_type=normalized_type,
            field="instrument_reference",
            message=(
                f"{normalized_type} requires authoritative cash instrument metadata; "
                "instrument classification is unavailable."
            ),
        )
    if not is_cash_instrument(product_type=product_type, asset_class=asset_class):
        raise CashAccountRequiredValidationError(
            reason_code=CashAccountRequiredValidationReasonCode.NON_CASH_INSTRUMENT,
            transaction_type=normalized_type,
            field="instrument_reference",
            message=(f"{normalized_type} must be represented as a cash instrument posting."),
        )


def _has_instrument_classification(*, product_type: object, asset_class: object) -> bool:
    return bool(
        normalize_transaction_control_code(product_type)
        or normalize_transaction_control_code(asset_class)
    )
