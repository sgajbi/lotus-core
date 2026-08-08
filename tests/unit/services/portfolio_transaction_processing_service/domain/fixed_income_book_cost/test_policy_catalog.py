"""Guard stable runtime amortized-cost policy methodology."""

from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    IFRS9_EIR_LOCAL_POLICY_ID,
    STRAIGHT_LINE_LOCAL_POLICY_ID,
    AmortizedCostMethod,
    AmortizedCostPolicyIdentity,
    AmortizedCostPolicyRegistry,
    YieldApplicationConvention,
    governed_amortized_cost_policy_catalog,
)


def test_catalog_exposes_versioned_effective_yield_and_straight_line_policies() -> None:
    policies = governed_amortized_cost_policy_catalog()
    registry = AmortizedCostPolicyRegistry(policies)

    assert registry.identities == (
        AmortizedCostPolicyIdentity(IFRS9_EIR_LOCAL_POLICY_ID, 1),
        AmortizedCostPolicyIdentity(STRAIGHT_LINE_LOCAL_POLICY_ID, 1),
    )
    effective_yield = registry.resolve(
        policy_id=IFRS9_EIR_LOCAL_POLICY_ID,
        policy_version=1,
    )
    assert effective_yield.method is AmortizedCostMethod.EFFECTIVE_YIELD
    assert (
        effective_yield.yield_application_convention
        is YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE
    )
    assert effective_yield.include_fees_in_amortized_cost is True
    assert effective_yield.residual_tolerance_local == Decimal("0.0000000001")

    straight_line = registry.resolve(
        policy_id=STRAIGHT_LINE_LOCAL_POLICY_ID,
        policy_version=1,
    )
    assert straight_line.method is AmortizedCostMethod.STRAIGHT_LINE
    assert straight_line.yield_application_convention is None
    assert straight_line.include_fees_in_amortized_cost is True
    assert straight_line.residual_tolerance_local == Decimal("0.0000000001")


def test_catalog_returns_new_immutable_values_without_identity_drift() -> None:
    first = governed_amortized_cost_policy_catalog()
    second = governed_amortized_cost_policy_catalog()

    assert first == second
    assert first is not second
    assert tuple((policy.policy_id, policy.policy_version) for policy in first) == (
        (IFRS9_EIR_LOCAL_POLICY_ID, 1),
        (STRAIGHT_LINE_LOCAL_POLICY_ID, 1),
    )
