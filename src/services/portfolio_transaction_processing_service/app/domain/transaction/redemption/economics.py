"""Resolve fixed-income redemption quantity, proceeds, and principal P&L."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Never, cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)

REDEMPTION_TRANSACTION_TYPES = frozenset(
    {"MATURITY_REDEMPTION", "CALL_REDEMPTION", "PARTIAL_REDEMPTION"}
)
_FULL_REDEMPTION_TRANSACTION_TYPES = frozenset({"MATURITY_REDEMPTION", "CALL_REDEMPTION"})
_ALGORITHM_ID = "fixed-income-redemption-economics"
_ALGORITHM_VERSION = 1


class RedemptionCalculationReasonCode(StrEnum):
    """Stable failure reasons for redemption input and reconciliation policy."""

    INVALID_TRANSACTION_TYPE = "REDEMPTION_001_INVALID_TRANSACTION_TYPE"
    NON_POSITIVE_POSITION_QUANTITY = "REDEMPTION_002_NON_POSITIVE_POSITION_QUANTITY"
    MISSING_QUANTITY_AUTHORITY = "REDEMPTION_003_MISSING_QUANTITY_AUTHORITY"
    INCOMPLETE_FACTOR_AUTHORITY = "REDEMPTION_004_INCOMPLETE_FACTOR_AUTHORITY"
    INVALID_FACTOR_TRANSITION = "REDEMPTION_005_INVALID_FACTOR_TRANSITION"
    NON_POSITIVE_REDEEMED_QUANTITY = "REDEMPTION_006_NON_POSITIVE_REDEEMED_QUANTITY"
    QUANTITY_EXCEEDS_POSITION = "REDEMPTION_007_QUANTITY_EXCEEDS_POSITION"
    FULL_REDEMPTION_QUANTITY_MISMATCH = "REDEMPTION_008_FULL_REDEMPTION_QUANTITY_MISMATCH"
    PARTIAL_REDEMPTION_CLOSES_POSITION = "REDEMPTION_009_PARTIAL_REDEMPTION_CLOSES_POSITION"
    QUANTITY_AUTHORITY_MISMATCH = "REDEMPTION_010_QUANTITY_AUTHORITY_MISMATCH"
    NON_POSITIVE_REDEMPTION_PRICE = "REDEMPTION_011_NON_POSITIVE_REDEMPTION_PRICE"
    PRINCIPAL_PROCEEDS_MISMATCH = "REDEMPTION_012_PRINCIPAL_PROCEEDS_MISMATCH"
    INVALID_MONETARY_INPUT = "REDEMPTION_013_INVALID_MONETARY_INPUT"
    NON_POSITIVE_FX_RATE = "REDEMPTION_014_NON_POSITIVE_FX_RATE"
    NEGATIVE_TOTAL_CASH_PROCEEDS = "REDEMPTION_015_NEGATIVE_TOTAL_CASH_PROCEEDS"
    INVALID_TOLERANCE = "REDEMPTION_016_INVALID_TOLERANCE"


class RedemptionCalculationError(ValueError):
    """Report one deterministic redemption calculation failure."""

    def __init__(
        self,
        code: RedemptionCalculationReasonCode,
        *,
        field: str,
        message: str,
    ) -> None:
        self.code = code
        self.field = field
        self.message = message
        super().__init__(f"{code.value}: {field}: {message}")


@dataclass(frozen=True, slots=True, kw_only=True)
class RedemptionTerms:
    """Source-owned terms and allocated book basis for one product redemption leg."""

    transaction_type: str
    position_quantity: Decimal
    redemption_price: Decimal
    allocated_cost_basis_local: Decimal
    allocated_cost_basis_base: Decimal
    fx_rate_to_base: Decimal
    redeemed_quantity: Decimal | None = None
    old_factor: Decimal | None = None
    new_factor: Decimal | None = None
    principal_proceeds_local: Decimal | None = None
    accrued_interest_proceeds_local: Decimal = Decimal(0)
    embedded_fee_amount_local: Decimal = Decimal(0)
    embedded_tax_amount_local: Decimal = Decimal(0)
    reconciliation_tolerance: Decimal = Decimal("0.0000000001")


@dataclass(frozen=True, slots=True)
class RedemptionEconomics:
    """Deterministic principal, cash, and realized-capital outputs with lineage."""

    redeemed_quantity: Decimal
    remaining_quantity: Decimal
    derived_principal_proceeds_local: Decimal
    principal_proceeds_local: Decimal
    accrued_interest_proceeds_local: Decimal
    total_cash_proceeds_local: Decimal
    principal_proceeds_base: Decimal
    realized_capital_pnl_local: Decimal
    realized_capital_pnl_base: Decimal
    calculation_lineage: CalculationLineage


def calculate_redemption_economics(terms: RedemptionTerms) -> RedemptionEconomics:
    """Calculate one redemption without inferring entitlement or mixing interest into P&L."""

    normalized = _validated_inputs(terms)
    quantity = _resolve_redeemed_quantity(normalized)
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    derived_principal = derive_redemption_principal_proceeds_local(
        quantity,
        normalized.redemption_price,
    )
    principal = _resolve_principal_proceeds(normalized, derived_principal)
    accrued_interest = policy.normalize(
        normalized.accrued_interest_proceeds_local,
        field_name="accrued_interest_proceeds_local",
    )
    embedded_fees = policy.normalize(
        normalized.embedded_fee_amount_local,
        field_name="embedded_fee_amount_local",
    )
    embedded_taxes = policy.normalize(
        normalized.embedded_tax_amount_local,
        field_name="embedded_tax_amount_local",
    )
    total_cash = policy.subtract(
        policy.add(
            principal,
            accrued_interest,
            field_name="gross_cash_proceeds_local",
        ),
        policy.add(
            embedded_fees,
            embedded_taxes,
            field_name="embedded_deductions_local",
        ),
        field_name="total_cash_proceeds_local",
    )
    if total_cash < Decimal(0):
        _fail(
            RedemptionCalculationReasonCode.NEGATIVE_TOTAL_CASH_PROCEEDS,
            "total_cash_proceeds_local",
            "principal plus interest must cover embedded fees and taxes.",
        )
    remaining_quantity = policy.subtract(
        normalized.position_quantity,
        quantity,
        field_name="remaining_quantity",
    )
    principal_base = policy.multiply(
        principal,
        normalized.fx_rate_to_base,
        field_name="principal_proceeds_base",
    )
    capital_pnl_local = policy.subtract(
        principal,
        normalized.allocated_cost_basis_local,
        field_name="realized_capital_pnl_local",
    )
    capital_pnl_base = policy.subtract(
        principal_base,
        normalized.allocated_cost_basis_base,
        field_name="realized_capital_pnl_base",
    )
    output = {
        "accrued_interest_proceeds_local": accrued_interest,
        "derived_principal_proceeds_local": derived_principal,
        "principal_proceeds_base": principal_base,
        "principal_proceeds_local": principal,
        "realized_capital_pnl_base": capital_pnl_base,
        "realized_capital_pnl_local": capital_pnl_local,
        "redeemed_quantity": quantity,
        "remaining_quantity": remaining_quantity,
        "total_cash_proceeds_local": total_cash,
    }
    lineage = build_calculation_lineage(
        algorithm_id=_ALGORITHM_ID,
        algorithm_version=_ALGORITHM_VERSION,
        intermediate_precision=policy.working_precision,
        input_payload=_lineage_input(normalized),
        output_payload=output,
        numeric_output_policy=policy.lineage_identity(),
    )
    return RedemptionEconomics(
        redeemed_quantity=quantity,
        remaining_quantity=remaining_quantity,
        derived_principal_proceeds_local=derived_principal,
        principal_proceeds_local=principal,
        accrued_interest_proceeds_local=accrued_interest,
        total_cash_proceeds_local=total_cash,
        principal_proceeds_base=principal_base,
        realized_capital_pnl_local=capital_pnl_local,
        realized_capital_pnl_base=capital_pnl_base,
        calculation_lineage=lineage,
    )


def derive_redemption_principal_proceeds_local(
    redeemed_quantity: Decimal,
    redemption_price: Decimal,
) -> Decimal:
    """Derive principal with the numeric policy bound by redemption economics lineage."""

    return cast(
        Decimal,
        TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            redeemed_quantity,
            redemption_price,
            field_name="derived_principal_proceeds_local",
        ),
    )


def _validated_inputs(terms: RedemptionTerms) -> RedemptionTerms:
    transaction_type = str(terms.transaction_type or "").strip().upper()
    if transaction_type not in REDEMPTION_TRANSACTION_TYPES:
        _fail(
            RedemptionCalculationReasonCode.INVALID_TRANSACTION_TYPE,
            "transaction_type",
            "transaction type must belong to the canonical redemption family.",
        )
    _require_positive(
        terms.position_quantity,
        code=RedemptionCalculationReasonCode.NON_POSITIVE_POSITION_QUANTITY,
        field="position_quantity",
    )
    _require_nonnegative(
        terms.redemption_price,
        code=RedemptionCalculationReasonCode.NON_POSITIVE_REDEMPTION_PRICE,
        field="redemption_price",
    )
    _require_positive(
        terms.fx_rate_to_base,
        code=RedemptionCalculationReasonCode.NON_POSITIVE_FX_RATE,
        field="fx_rate_to_base",
    )
    _require_nonnegative(
        terms.reconciliation_tolerance,
        code=RedemptionCalculationReasonCode.INVALID_TOLERANCE,
        field="reconciliation_tolerance",
    )
    for field in (
        "allocated_cost_basis_local",
        "allocated_cost_basis_base",
        "accrued_interest_proceeds_local",
        "embedded_fee_amount_local",
        "embedded_tax_amount_local",
    ):
        _require_nonnegative(
            getattr(terms, field),
            code=RedemptionCalculationReasonCode.INVALID_MONETARY_INPUT,
            field=field,
        )
    if terms.principal_proceeds_local is not None:
        _require_nonnegative(
            terms.principal_proceeds_local,
            code=RedemptionCalculationReasonCode.INVALID_MONETARY_INPUT,
            field="principal_proceeds_local",
        )
    if terms.redeemed_quantity is not None:
        _require_positive(
            terms.redeemed_quantity,
            code=RedemptionCalculationReasonCode.NON_POSITIVE_REDEEMED_QUANTITY,
            field="redeemed_quantity",
        )
    return replace(terms, transaction_type=transaction_type)


def _resolve_redeemed_quantity(terms: RedemptionTerms) -> Decimal:
    explicit = terms.redeemed_quantity
    factor_quantity = _factor_redeemed_quantity(terms)
    if explicit is not None and factor_quantity is not None:
        _require_within_tolerance(
            explicit,
            factor_quantity,
            terms.reconciliation_tolerance,
            code=RedemptionCalculationReasonCode.QUANTITY_AUTHORITY_MISMATCH,
            field="redeemed_quantity",
        )
    if explicit is None:
        if factor_quantity is None:
            _fail(
                RedemptionCalculationReasonCode.MISSING_QUANTITY_AUTHORITY,
                "redeemed_quantity",
                "redeemed quantity or a complete old/new factor transition is required.",
            )
        quantity = factor_quantity
    else:
        quantity = explicit
    if quantity > terms.position_quantity:
        _fail(
            RedemptionCalculationReasonCode.QUANTITY_EXCEEDS_POSITION,
            "redeemed_quantity",
            "redeemed quantity must not exceed the available position quantity.",
        )
    if terms.transaction_type in _FULL_REDEMPTION_TRANSACTION_TYPES:
        _require_within_tolerance(
            quantity,
            terms.position_quantity,
            terms.reconciliation_tolerance,
            code=RedemptionCalculationReasonCode.FULL_REDEMPTION_QUANTITY_MISMATCH,
            field="redeemed_quantity",
        )
    elif quantity >= terms.position_quantity:
        _fail(
            RedemptionCalculationReasonCode.PARTIAL_REDEMPTION_CLOSES_POSITION,
            "redeemed_quantity",
            "PARTIAL_REDEMPTION must leave a positive remaining position.",
        )
    return cast(
        Decimal,
        TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
            quantity,
            field_name="redeemed_quantity",
        ),
    )


def _factor_redeemed_quantity(terms: RedemptionTerms) -> Decimal | None:
    old_factor = terms.old_factor
    new_factor = terms.new_factor
    if old_factor is None and new_factor is None:
        return None
    if old_factor is None or new_factor is None:
        _fail(
            RedemptionCalculationReasonCode.INCOMPLETE_FACTOR_AUTHORITY,
            "old_factor",
            "old_factor and new_factor must be supplied together.",
        )
    if (
        not isinstance(old_factor, Decimal)
        or not isinstance(new_factor, Decimal)
        or not old_factor.is_finite()
        or not new_factor.is_finite()
        or old_factor <= Decimal(0)
        or new_factor < Decimal(0)
        or new_factor >= old_factor
    ):
        _fail(
            RedemptionCalculationReasonCode.INVALID_FACTOR_TRANSITION,
            "new_factor",
            "factor transition requires 0 <= new_factor < old_factor.",
        )
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    with policy.arithmetic_context():
        factor_quantity = terms.position_quantity * (old_factor - new_factor) / old_factor
    return cast(
        Decimal,
        policy.normalize(
            factor_quantity,
            field_name="factor_redeemed_quantity",
        ),
    )


def _resolve_principal_proceeds(terms: RedemptionTerms, derived: Decimal) -> Decimal:
    if terms.principal_proceeds_local is None:
        return derived
    _require_within_tolerance(
        terms.principal_proceeds_local,
        derived,
        terms.reconciliation_tolerance,
        code=RedemptionCalculationReasonCode.PRINCIPAL_PROCEEDS_MISMATCH,
        field="principal_proceeds_local",
    )
    return cast(
        Decimal,
        TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
            terms.principal_proceeds_local,
            field_name="principal_proceeds_local",
        ),
    )


def _require_within_tolerance(
    left: Decimal,
    right: Decimal,
    tolerance: Decimal,
    *,
    code: RedemptionCalculationReasonCode,
    field: str,
) -> None:
    if abs(left - right) > tolerance:
        _fail(code, field, f"values differ by more than the governed tolerance {tolerance}.")


def _require_positive(
    value: Decimal,
    *,
    code: RedemptionCalculationReasonCode,
    field: str,
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= Decimal(0):
        _fail(code, field, "value must be a positive finite decimal.")


def _require_nonnegative(
    value: Decimal,
    *,
    code: RedemptionCalculationReasonCode,
    field: str,
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < Decimal(0):
        _fail(code, field, "value must be a non-negative finite decimal.")


def _lineage_input(terms: RedemptionTerms) -> dict[str, object]:
    return {field: getattr(terms, field) for field in terms.__dataclass_fields__}


def _fail(code: RedemptionCalculationReasonCode, field: str, message: str) -> Never:
    raise RedemptionCalculationError(code, field=field, message=message)
