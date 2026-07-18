"""Tests for exact, versioned supported valuation-policy resolution."""

from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import (
    AccruedIncomeTreatment,
    PositionScaling,
    PrincipalBasis,
    UnknownValuationPolicyError,
    ValuationInputBasis,
    ValuationOutputMeasure,
    resolve_position_valuation_policy,
    supported_position_valuation_policies,
)


def test_supported_policy_keys_are_unique_and_stably_ordered() -> None:
    policies = supported_position_valuation_policies()
    keys = [(policy.policy_id, policy.policy_version) for policy in policies]

    assert len(policies) == 16
    assert len(set(keys)) == len(keys)
    assert keys[0] == ("UNIT_PRICE_MARKET_VALUE", 1)
    assert keys[-1] == ("SUPPLIED_WHOLE_POSITION_SETTLEMENT_VARIATION", 1)


def test_resolution_requires_exact_identifier_and_version() -> None:
    policy = resolve_position_valuation_policy(" UNIT_PRICE_MARKET_VALUE ", 1)

    assert policy.input_basis is ValuationInputBasis.UNIT_PRICE
    assert policy.position_scaling is PositionScaling.QUANTITY

    with pytest.raises(UnknownValuationPolicyError, match="@2"):
        resolve_position_valuation_policy("UNIT_PRICE_MARKET_VALUE", 2)
    with pytest.raises(UnknownValuationPolicyError, match="unsupported valuation policy"):
        resolve_position_valuation_policy("EQUITY", 1)


@pytest.mark.parametrize(
    ("policy_id", "principal_basis", "accrued"),
    [
        (
            "CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL",
            PrincipalBasis.FACE_AMOUNT,
            AccruedIncomeTreatment.CALCULATED_SEPARATELY,
        ),
        (
            "CLEAN_PERCENT_FACTOR_SUPPLIED_ACCRUAL",
            PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL,
            AccruedIncomeTreatment.SUPPLIED_SEPARATELY,
        ),
        (
            "DIRTY_PERCENT_CURRENT_PRINCIPAL_MARKET_VALUE",
            PrincipalBasis.SUPPLIED_CURRENT_PRINCIPAL,
            AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE,
        ),
    ],
)
def test_percent_of_principal_policies_declare_basis_accrual_and_denominator(
    policy_id: str,
    principal_basis: PrincipalBasis,
    accrued: AccruedIncomeTreatment,
) -> None:
    policy = resolve_position_valuation_policy(policy_id, 1)

    assert policy.principal_basis is principal_basis
    assert policy.accrued_income_treatment is accrued
    assert policy.position_scaling is PositionScaling.PRINCIPAL
    assert policy.quote_denominator == Decimal("100")


def test_derivative_outputs_are_not_implicitly_market_value() -> None:
    notional = resolve_position_valuation_policy("FUTURES_NOTIONAL_PER_UNDERLYING_UNIT", 1)
    settlement = resolve_position_valuation_policy(
        "SUPPLIED_WHOLE_POSITION_SETTLEMENT_VARIATION", 1
    )

    assert notional.output_measure is ValuationOutputMeasure.NOTIONAL_EXPOSURE
    assert settlement.output_measure is ValuationOutputMeasure.SETTLEMENT_VARIATION


@pytest.mark.parametrize(("policy_id", "version"), [("", 1), ("   ", 1), ("POLICY", 0)])
def test_invalid_lookup_identity_is_rejected(policy_id: str, version: int) -> None:
    with pytest.raises(ValueError):
        resolve_position_valuation_policy(policy_id, version)
