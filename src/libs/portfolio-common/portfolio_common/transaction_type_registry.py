"""Canonical transaction type registry for Lotus booking semantics.

This registry is the reviewable source of transaction-type classification. Runtime engines may
adopt it incrementally, but local transaction-type enums and rule tables must stay covered here so
unknown or target-only types cannot silently drift through one layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

SUPPORTED = "supported"
LIMITED = "limited"
DEFAULT_STRATEGY = "default_strategy"
INTERNAL_GENERATED = "internal_generated"
TARGET_NOT_IMPLEMENTED = "target_not_implemented"
MIGRATION_ONLY = "migration_only"


@dataclass(frozen=True)
class TransactionTypeDefinition:
    code: str
    lifecycle_family: str
    economic_role: str
    position_effect: str
    cash_effect: str
    lot_behavior: str
    settlement_behavior: str
    calculation_support_status: str
    production_booking_allowed: bool


def _definition(
    code: str,
    *,
    lifecycle_family: str,
    economic_role: str,
    position_effect: str,
    cash_effect: str,
    lot_behavior: str,
    settlement_behavior: str,
    calculation_support_status: str = SUPPORTED,
    production_booking_allowed: bool = True,
) -> TransactionTypeDefinition:
    return TransactionTypeDefinition(
        code=code,
        lifecycle_family=lifecycle_family,
        economic_role=economic_role,
        position_effect=position_effect,
        cash_effect=cash_effect,
        lot_behavior=lot_behavior,
        settlement_behavior=settlement_behavior,
        calculation_support_status=calculation_support_status,
        production_booking_allowed=production_booking_allowed,
    )


_REGISTRY: dict[str, TransactionTypeDefinition] = {
    "BUY": _definition(
        "BUY",
        lifecycle_family="trade",
        economic_role="security_buy",
        position_effect="increase",
        cash_effect="outflow",
        lot_behavior="open_lot",
        settlement_behavior="requires_cash_leg",
    ),
    "SELL": _definition(
        "SELL",
        lifecycle_family="trade",
        economic_role="security_sell",
        position_effect="decrease",
        cash_effect="inflow",
        lot_behavior="consume_lot",
        settlement_behavior="requires_cash_leg",
    ),
    "FX_SPOT": _definition(
        "FX_SPOT",
        lifecycle_family="fx",
        economic_role="fx_trade",
        position_effect="none",
        cash_effect="linked_cash_legs",
        lot_behavior="none",
        settlement_behavior="requires_cash_leg",
    ),
    "FX_FORWARD": _definition(
        "FX_FORWARD",
        lifecycle_family="fx",
        economic_role="fx_forward",
        position_effect="none",
        cash_effect="linked_cash_legs",
        lot_behavior="none",
        settlement_behavior="requires_cash_leg",
    ),
    "FX_SWAP": _definition(
        "FX_SWAP",
        lifecycle_family="fx",
        economic_role="fx_swap",
        position_effect="none",
        cash_effect="linked_cash_legs",
        lot_behavior="none",
        settlement_behavior="requires_cash_leg",
    ),
    "INTEREST": _definition(
        "INTEREST",
        lifecycle_family="income",
        economic_role="income_receipt",
        position_effect="none",
        cash_effect="inflow",
        lot_behavior="none",
        settlement_behavior="requires_cash_leg",
    ),
    "DIVIDEND": _definition(
        "DIVIDEND",
        lifecycle_family="income",
        economic_role="income_receipt",
        position_effect="none",
        cash_effect="inflow",
        lot_behavior="none",
        settlement_behavior="requires_cash_leg",
    ),
    "DEPOSIT": _definition(
        "DEPOSIT",
        lifecycle_family="cash_movement",
        economic_role="cash_deposit",
        position_effect="cash_increase",
        cash_effect="inflow",
        lot_behavior="none",
        settlement_behavior="cash_account_required",
    ),
    "WITHDRAWAL": _definition(
        "WITHDRAWAL",
        lifecycle_family="cash_movement",
        economic_role="cash_withdrawal",
        position_effect="cash_decrease",
        cash_effect="outflow",
        lot_behavior="none",
        settlement_behavior="cash_account_required",
    ),
    "FEE": _definition(
        "FEE",
        lifecycle_family="expense",
        economic_role="fee",
        position_effect="cash_decrease",
        cash_effect="outflow",
        lot_behavior="none",
        settlement_behavior="cash_account_required",
        calculation_support_status=LIMITED,
    ),
    "TAX": _definition(
        "TAX",
        lifecycle_family="expense",
        economic_role="tax",
        position_effect="cash_decrease",
        cash_effect="outflow",
        lot_behavior="none",
        settlement_behavior="cash_account_required",
        calculation_support_status=LIMITED,
    ),
    "TRANSFER_IN": _definition(
        "TRANSFER_IN",
        lifecycle_family="transfer",
        economic_role="security_transfer_in",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="preserve_or_restate_lot",
        settlement_behavior="not_applicable",
    ),
    "TRANSFER_OUT": _definition(
        "TRANSFER_OUT",
        lifecycle_family="transfer",
        economic_role="security_transfer_out",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="preserve_or_consume_lot",
        settlement_behavior="not_applicable",
    ),
    "MERGER_OUT": _definition(
        "MERGER_OUT",
        lifecycle_family="corporate_action",
        economic_role="source_security_leg",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="transfer_basis_out",
        settlement_behavior="not_applicable",
    ),
    "MERGER_IN": _definition(
        "MERGER_IN",
        lifecycle_family="corporate_action",
        economic_role="target_security_leg",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="transfer_basis_in",
        settlement_behavior="not_applicable",
    ),
    "EXCHANGE_OUT": _definition(
        "EXCHANGE_OUT",
        lifecycle_family="corporate_action",
        economic_role="source_security_leg",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="transfer_basis_out",
        settlement_behavior="not_applicable",
    ),
    "EXCHANGE_IN": _definition(
        "EXCHANGE_IN",
        lifecycle_family="corporate_action",
        economic_role="target_security_leg",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="transfer_basis_in",
        settlement_behavior="not_applicable",
    ),
    "REPLACEMENT_OUT": _definition(
        "REPLACEMENT_OUT",
        lifecycle_family="corporate_action",
        economic_role="source_security_leg",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="transfer_basis_out",
        settlement_behavior="not_applicable",
    ),
    "REPLACEMENT_IN": _definition(
        "REPLACEMENT_IN",
        lifecycle_family="corporate_action",
        economic_role="target_security_leg",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="transfer_basis_in",
        settlement_behavior="not_applicable",
    ),
    "SPIN_OFF": _definition(
        "SPIN_OFF",
        lifecycle_family="corporate_action",
        economic_role="source_security_reduction",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="partial_basis_transfer",
        settlement_behavior="not_applicable",
    ),
    "SPIN_IN": _definition(
        "SPIN_IN",
        lifecycle_family="corporate_action",
        economic_role="target_security_leg",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="basis_allocation_in",
        settlement_behavior="not_applicable",
    ),
    "DEMERGER_OUT": _definition(
        "DEMERGER_OUT",
        lifecycle_family="corporate_action",
        economic_role="source_security_reduction",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="partial_basis_transfer",
        settlement_behavior="not_applicable",
    ),
    "DEMERGER_IN": _definition(
        "DEMERGER_IN",
        lifecycle_family="corporate_action",
        economic_role="target_security_leg",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="basis_allocation_in",
        settlement_behavior="not_applicable",
    ),
    "CASH_CONSIDERATION": _definition(
        "CASH_CONSIDERATION",
        lifecycle_family="corporate_action",
        economic_role="cash_consideration",
        position_effect="none",
        cash_effect="inflow",
        lot_behavior="none",
        settlement_behavior="requires_cash_leg",
    ),
    "CASH_IN_LIEU": _definition(
        "CASH_IN_LIEU",
        lifecycle_family="corporate_action",
        economic_role="fractional_cash_settlement",
        position_effect="decrease",
        cash_effect="inflow",
        lot_behavior="consume_lot",
        settlement_behavior="requires_cash_leg",
    ),
    "SPLIT": _definition(
        "SPLIT",
        lifecycle_family="corporate_action",
        economic_role="quantity_restatement",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="quantity_restatement",
        settlement_behavior="not_applicable",
    ),
    "REVERSE_SPLIT": _definition(
        "REVERSE_SPLIT",
        lifecycle_family="corporate_action",
        economic_role="quantity_restatement",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="quantity_restatement",
        settlement_behavior="not_applicable",
    ),
    "CONSOLIDATION": _definition(
        "CONSOLIDATION",
        lifecycle_family="corporate_action",
        economic_role="quantity_restatement",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="quantity_restatement",
        settlement_behavior="not_applicable",
    ),
    "BONUS_ISSUE": _definition(
        "BONUS_ISSUE",
        lifecycle_family="corporate_action",
        economic_role="quantity_restatement",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="quantity_restatement",
        settlement_behavior="not_applicable",
    ),
    "STOCK_DIVIDEND": _definition(
        "STOCK_DIVIDEND",
        lifecycle_family="corporate_action",
        economic_role="quantity_restatement",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="quantity_restatement",
        settlement_behavior="not_applicable",
    ),
    "RIGHTS_ANNOUNCE": _definition(
        "RIGHTS_ANNOUNCE",
        lifecycle_family="rights",
        economic_role="rights_notification",
        position_effect="none",
        cash_effect="none",
        lot_behavior="none",
        settlement_behavior="not_applicable",
        calculation_support_status=DEFAULT_STRATEGY,
    ),
    "RIGHTS_ALLOCATE": _definition(
        "RIGHTS_ALLOCATE",
        lifecycle_family="rights",
        economic_role="rights_allocation",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="open_rights_lot",
        settlement_behavior="not_applicable",
    ),
    "RIGHTS_EXPIRE": _definition(
        "RIGHTS_EXPIRE",
        lifecycle_family="rights",
        economic_role="rights_expiry",
        position_effect="decrease",
        cash_effect="none",
        lot_behavior="consume_rights_lot",
        settlement_behavior="not_applicable",
    ),
    "RIGHTS_ADJUSTMENT": _definition(
        "RIGHTS_ADJUSTMENT",
        lifecycle_family="rights",
        economic_role="rights_adjustment",
        position_effect="none",
        cash_effect="none",
        lot_behavior="policy_adjustment",
        settlement_behavior="not_applicable",
        calculation_support_status=DEFAULT_STRATEGY,
    ),
    "RIGHTS_SELL": _definition(
        "RIGHTS_SELL",
        lifecycle_family="rights",
        economic_role="rights_sale",
        position_effect="decrease",
        cash_effect="inflow",
        lot_behavior="consume_rights_lot",
        settlement_behavior="requires_cash_leg",
    ),
    "RIGHTS_SUBSCRIBE": _definition(
        "RIGHTS_SUBSCRIBE",
        lifecycle_family="rights",
        economic_role="rights_subscription",
        position_effect="decrease",
        cash_effect="outflow",
        lot_behavior="consume_rights_lot",
        settlement_behavior="requires_cash_leg",
    ),
    "RIGHTS_OVERSUBSCRIBE": _definition(
        "RIGHTS_OVERSUBSCRIBE",
        lifecycle_family="rights",
        economic_role="rights_oversubscription",
        position_effect="decrease",
        cash_effect="outflow",
        lot_behavior="consume_rights_lot",
        settlement_behavior="requires_cash_leg",
    ),
    "RIGHTS_REFUND": _definition(
        "RIGHTS_REFUND",
        lifecycle_family="rights",
        economic_role="rights_refund",
        position_effect="none",
        cash_effect="inflow",
        lot_behavior="none",
        settlement_behavior="requires_cash_leg",
    ),
    "RIGHTS_SHARE_DELIVERY": _definition(
        "RIGHTS_SHARE_DELIVERY",
        lifecycle_family="rights",
        economic_role="rights_share_delivery",
        position_effect="increase",
        cash_effect="none",
        lot_behavior="open_lot",
        settlement_behavior="not_applicable",
    ),
    "ADJUSTMENT": _definition(
        "ADJUSTMENT",
        lifecycle_family="adjustment",
        economic_role="cash_or_position_adjustment",
        position_effect="mixed",
        cash_effect="mixed",
        lot_behavior="policy_adjustment",
        settlement_behavior="conditional",
        calculation_support_status=DEFAULT_STRATEGY,
    ),
    "FX_CASH_SETTLEMENT_BUY": _definition(
        "FX_CASH_SETTLEMENT_BUY",
        lifecycle_family="fx",
        economic_role="generated_fx_cash_leg",
        position_effect="cash_increase",
        cash_effect="inflow",
        lot_behavior="none",
        settlement_behavior="cash_account_required",
        calculation_support_status=INTERNAL_GENERATED,
        production_booking_allowed=False,
    ),
    "FX_CASH_SETTLEMENT_SELL": _definition(
        "FX_CASH_SETTLEMENT_SELL",
        lifecycle_family="fx",
        economic_role="generated_fx_cash_leg",
        position_effect="cash_decrease",
        cash_effect="outflow",
        lot_behavior="none",
        settlement_behavior="cash_account_required",
        calculation_support_status=INTERNAL_GENERATED,
        production_booking_allowed=False,
    ),
    "OTHER": _definition(
        "OTHER",
        lifecycle_family="migration",
        economic_role="unknown_legacy_type",
        position_effect="unknown",
        cash_effect="unknown",
        lot_behavior="unknown",
        settlement_behavior="unknown",
        calculation_support_status=MIGRATION_ONLY,
        production_booking_allowed=False,
    ),
}

_TARGET_NOT_IMPLEMENTED_TYPES = {
    "MATURITY_REDEMPTION": ("redemption", "maturity_redemption"),
    "CALL_REDEMPTION": ("redemption", "call_redemption"),
    "PARTIAL_REDEMPTION": ("redemption", "partial_redemption"),
    "AMORTIZATION": ("redemption", "principal_amortization"),
    "ACCRETION": ("redemption", "discount_accretion"),
    "CONVERSION_EVENT": ("conversion", "parent_conversion_event"),
    "CONVERSION_OUT": ("conversion", "source_security_leg"),
    "CONVERSION_IN": ("conversion", "target_security_leg"),
    "EXERCISE_OUT": ("conversion", "source_contract_leg"),
    "EXERCISE_IN": ("conversion", "target_security_leg"),
    "STRIKE_PAYMENT": ("conversion", "strike_cash_payment"),
}

for _code, (_family, _role) in _TARGET_NOT_IMPLEMENTED_TYPES.items():
    _REGISTRY[_code] = _definition(
        _code,
        lifecycle_family=_family,
        economic_role=_role,
        position_effect="target_model_required",
        cash_effect="target_model_required",
        lot_behavior="target_model_required",
        settlement_behavior="target_model_required",
        calculation_support_status=TARGET_NOT_IMPLEMENTED,
        production_booking_allowed=False,
    )

TRANSACTION_TYPE_REGISTRY: Mapping[str, TransactionTypeDefinition] = MappingProxyType(
    dict(sorted(_REGISTRY.items()))
)
TRANSACTION_TYPE_CODES = frozenset(TRANSACTION_TYPE_REGISTRY)
PRODUCTION_BOOKING_TRANSACTION_TYPES = frozenset(
    code
    for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    if definition.production_booking_allowed
)
TARGET_NOT_IMPLEMENTED_TRANSACTION_TYPES = frozenset(_TARGET_NOT_IMPLEMENTED_TYPES)


def get_transaction_type_definition(code: str) -> TransactionTypeDefinition | None:
    normalized = str(code or "").strip().upper()
    return TRANSACTION_TYPE_REGISTRY.get(normalized)


def is_registered_transaction_type(code: str) -> bool:
    return get_transaction_type_definition(code) is not None


def is_production_booking_transaction_type(code: str) -> bool:
    definition = get_transaction_type_definition(code)
    return bool(definition and definition.production_booking_allowed)


def require_registered_transaction_type(code: str) -> TransactionTypeDefinition:
    normalized = str(code or "").strip().upper()
    definition = TRANSACTION_TYPE_REGISTRY.get(normalized)
    if definition is None:
        raise ValueError(f"Unknown transaction type: {normalized or '<blank>'}")
    return definition
