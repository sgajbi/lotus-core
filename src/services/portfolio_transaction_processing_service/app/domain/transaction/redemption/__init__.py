"""Canonical fixed-income redemption economics and validation."""

from .economics import (
    REDEMPTION_TRANSACTION_TYPES,
    RedemptionCalculationError,
    RedemptionCalculationReasonCode,
    RedemptionEconomics,
    RedemptionTerms,
    calculate_redemption_economics,
    derive_redemption_principal_proceeds_local,
)

__all__ = [
    "REDEMPTION_TRANSACTION_TYPES",
    "RedemptionCalculationError",
    "RedemptionCalculationReasonCode",
    "RedemptionEconomics",
    "RedemptionTerms",
    "calculate_redemption_economics",
    "derive_redemption_principal_proceeds_local",
]
