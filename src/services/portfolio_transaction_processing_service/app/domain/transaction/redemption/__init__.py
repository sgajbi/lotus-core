"""Canonical fixed-income redemption economics and validation."""

from .accrued_interest import (
    REDEMPTION_ACCRUED_INTEREST_COMPONENT,
    build_redemption_accrued_interest_component,
    is_generated_redemption_accrued_interest,
    neutralize_generated_redemption_accrued_interest,
    redemption_accrued_interest_transaction_id,
)
from .economics import (
    REDEMPTION_TRANSACTION_TYPES,
    RedemptionCalculationError,
    RedemptionCalculationReasonCode,
    RedemptionEconomics,
    RedemptionTerms,
    calculate_redemption_economics,
    derive_redemption_principal_proceeds_local,
)
from .linked_event_validation import (
    RedemptionLinkedEventValidationError,
    RedemptionLinkedEventValidationReasonCode,
    assert_linked_redemption_interest_unambiguous,
    requires_linked_redemption_interest_history,
)

__all__ = [
    "REDEMPTION_ACCRUED_INTEREST_COMPONENT",
    "REDEMPTION_TRANSACTION_TYPES",
    "RedemptionCalculationError",
    "RedemptionCalculationReasonCode",
    "RedemptionEconomics",
    "RedemptionLinkedEventValidationError",
    "RedemptionLinkedEventValidationReasonCode",
    "RedemptionTerms",
    "assert_linked_redemption_interest_unambiguous",
    "build_redemption_accrued_interest_component",
    "calculate_redemption_economics",
    "derive_redemption_principal_proceeds_local",
    "is_generated_redemption_accrued_interest",
    "neutralize_generated_redemption_accrued_interest",
    "requires_linked_redemption_interest_history",
    "redemption_accrued_interest_transaction_id",
]
