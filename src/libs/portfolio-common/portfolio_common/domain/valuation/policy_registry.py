"""Versioned registry for supported position-valuation policy compositions."""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType

from .position_valuation import (
    AccruedIncomeTreatment,
    FxConversionPolicy,
    PositionScaling,
    PositionValuationPolicy,
    PrincipalBasis,
    ValuationInputBasis,
    ValuationOutputMeasure,
)


class UnknownValuationPolicyError(LookupError):
    """Raised when an assignment references an unsupported policy definition."""


def _policy(
    policy_id: str,
    *,
    input_basis: ValuationInputBasis,
    principal_basis: PrincipalBasis = PrincipalBasis.POSITION_UNITS,
    scaling: PositionScaling = PositionScaling.QUANTITY,
    accrued: AccruedIncomeTreatment = AccruedIncomeTreatment.NOT_APPLICABLE,
    output: ValuationOutputMeasure = ValuationOutputMeasure.MARKET_VALUE,
    quote_denominator: Decimal | None = None,
) -> PositionValuationPolicy:
    return PositionValuationPolicy(
        policy_id=policy_id,
        policy_version=1,
        input_basis=input_basis,
        principal_basis=principal_basis,
        position_scaling=scaling,
        accrued_income_treatment=accrued,
        fx_conversion=FxConversionPolicy.DIRECT_SOURCE_TO_REPORTING,
        output_measure=output,
        quote_denominator=quote_denominator,
    )


def _principal_policy(
    policy_id: str,
    *,
    input_basis: ValuationInputBasis,
    principal_basis: PrincipalBasis,
    accrued: AccruedIncomeTreatment,
) -> PositionValuationPolicy:
    return _policy(
        policy_id,
        input_basis=input_basis,
        principal_basis=principal_basis,
        scaling=PositionScaling.PRINCIPAL,
        accrued=accrued,
        quote_denominator=Decimal("100"),
    )


_SUPPORTED_POLICIES = (
    _policy("UNIT_PRICE_MARKET_VALUE", input_basis=ValuationInputBasis.UNIT_PRICE),
    _policy("NAV_PER_UNIT_MARKET_VALUE", input_basis=ValuationInputBasis.NAV_PER_UNIT),
    _principal_policy(
        "CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.FACE_AMOUNT,
        accrued=AccruedIncomeTreatment.CALCULATED_SEPARATELY,
    ),
    _principal_policy(
        "CLEAN_PERCENT_FACE_SUPPLIED_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.FACE_AMOUNT,
        accrued=AccruedIncomeTreatment.SUPPLIED_SEPARATELY,
    ),
    _principal_policy(
        "DIRTY_PERCENT_FACE_MARKET_VALUE",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY,
        principal_basis=PrincipalBasis.FACE_AMOUNT,
        accrued=AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE,
    ),
    _principal_policy(
        "CLEAN_PERCENT_FACE_NO_PERIODIC_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.FACE_AMOUNT,
        accrued=AccruedIncomeTreatment.NO_PERIODIC_ACCRUAL,
    ),
    _principal_policy(
        "CLEAN_PERCENT_FACTOR_CALCULATED_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.CALCULATED_SEPARATELY,
    ),
    _principal_policy(
        "CLEAN_PERCENT_FACTOR_SUPPLIED_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.SUPPLIED_SEPARATELY,
    ),
    _principal_policy(
        "DIRTY_PERCENT_FACTOR_MARKET_VALUE",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY,
        principal_basis=PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE,
    ),
    _principal_policy(
        "CLEAN_PERCENT_FACTOR_NO_PERIODIC_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.NO_PERIODIC_ACCRUAL,
    ),
    _principal_policy(
        "CLEAN_PERCENT_CURRENT_PRINCIPAL_CALCULATED_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.SUPPLIED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.CALCULATED_SEPARATELY,
    ),
    _principal_policy(
        "CLEAN_PERCENT_CURRENT_PRINCIPAL_SUPPLIED_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.SUPPLIED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.SUPPLIED_SEPARATELY,
    ),
    _principal_policy(
        "DIRTY_PERCENT_CURRENT_PRINCIPAL_MARKET_VALUE",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY,
        principal_basis=PrincipalBasis.SUPPLIED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE,
    ),
    _principal_policy(
        "CLEAN_PERCENT_CURRENT_PRINCIPAL_NO_PERIODIC_ACCRUAL",
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.SUPPLIED_CURRENT_PRINCIPAL,
        accrued=AccruedIncomeTreatment.NO_PERIODIC_ACCRUAL,
    ),
    _policy(
        "SUPPLIED_PER_UNDERLYING_UNIT_MARKET_VALUE",
        input_basis=ValuationInputBasis.SUPPLIED_VALUE_PER_UNDERLYING_UNIT,
        scaling=PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER,
    ),
    _policy(
        "SUPPLIED_PER_CONTRACT_MARKET_VALUE",
        input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_PER_CONTRACT,
    ),
    _policy(
        "SUPPLIED_WHOLE_POSITION_MARKET_VALUE",
        input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_WHOLE_POSITION,
        scaling=PositionScaling.NONE,
    ),
    _policy(
        "FUTURES_NOTIONAL_PER_UNDERLYING_UNIT",
        input_basis=ValuationInputBasis.SUPPLIED_VALUE_PER_UNDERLYING_UNIT,
        scaling=PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER,
        output=ValuationOutputMeasure.NOTIONAL_EXPOSURE,
    ),
    _policy(
        "SUPPLIED_WHOLE_POSITION_SETTLEMENT_VARIATION",
        input_basis=ValuationInputBasis.SETTLEMENT_VARIATION_WHOLE_POSITION,
        scaling=PositionScaling.NONE,
        output=ValuationOutputMeasure.SETTLEMENT_VARIATION,
    ),
)

_POLICIES_BY_KEY = MappingProxyType(
    {(policy.policy_id, policy.policy_version): policy for policy in _SUPPORTED_POLICIES}
)
if len(_POLICIES_BY_KEY) != len(_SUPPORTED_POLICIES):
    raise RuntimeError("valuation policy registry contains duplicate policy id/version keys")


def supported_position_valuation_policies() -> tuple[PositionValuationPolicy, ...]:
    """Return the immutable supported policy catalog in stable declaration order."""

    return _SUPPORTED_POLICIES


def resolve_position_valuation_policy(
    policy_id: str,
    policy_version: int,
) -> PositionValuationPolicy:
    """Resolve one exact policy id/version without default or version fallback."""

    normalized_policy_id = policy_id.strip()
    if not normalized_policy_id:
        raise ValueError("policy_id must be nonblank")
    if policy_version < 1:
        raise ValueError("policy_version must be positive")
    try:
        return _POLICIES_BY_KEY[(normalized_policy_id, policy_version)]
    except KeyError as error:
        raise UnknownValuationPolicyError(
            f"unsupported valuation policy: {normalized_policy_id}@{policy_version}"
        ) from error
