"""Verify fixed-income book-cost policy selection remains explicit and version exact."""

from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizedCostMethod,
    AmortizedCostPolicy,
    AmortizedCostPolicyIdentity,
    AmortizedCostPolicyRegistry,
    DuplicateAmortizedCostPolicyError,
    UnsupportedAmortizedCostPolicyError,
    YieldApplicationConvention,
)


def _policy(
    *,
    policy_id: str = "IFRS9_EIR_LOCAL",
    policy_version: int = 1,
) -> AmortizedCostPolicy:
    return AmortizedCostPolicy(
        policy_id=policy_id,
        policy_version=policy_version,
        method=AmortizedCostMethod.EFFECTIVE_YIELD,
        yield_application_convention=YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
        include_fees_in_amortized_cost=True,
        residual_tolerance_local=Decimal("0.0000000001"),
    )


def test_resolve_requires_exact_policy_identity() -> None:
    policy_v1 = _policy()
    policy_v2 = _policy(policy_version=2)
    registry = AmortizedCostPolicyRegistry((policy_v2, policy_v1))

    assert registry.resolve(policy_id=" IFRS9_EIR_LOCAL ", policy_version=1) is policy_v1
    assert registry.resolve(policy_id="IFRS9_EIR_LOCAL", policy_version=2) is policy_v2
    assert registry.identities == (
        AmortizedCostPolicyIdentity("IFRS9_EIR_LOCAL", 1),
        AmortizedCostPolicyIdentity("IFRS9_EIR_LOCAL", 2),
    )


@pytest.mark.parametrize(
    ("policy_id", "policy_version"),
    (("UNKNOWN", 1), ("IFRS9_EIR_LOCAL", 3), ("ifrs9_eir_local", 1)),
)
def test_resolve_does_not_fallback_by_name_case_or_version(
    policy_id: str,
    policy_version: int,
) -> None:
    registry = AmortizedCostPolicyRegistry((_policy(),))

    with pytest.raises(
        UnsupportedAmortizedCostPolicyError,
        match=f"{policy_id.strip()}@{policy_version}",
    ):
        registry.resolve(policy_id=policy_id, policy_version=policy_version)


def test_duplicate_identity_is_rejected_even_when_semantics_match() -> None:
    with pytest.raises(
        DuplicateAmortizedCostPolicyError,
        match="IFRS9_EIR_LOCAL@1",
    ):
        AmortizedCostPolicyRegistry((_policy(), _policy()))


@pytest.mark.parametrize("invalid", (None, "IFRS9_EIR_LOCAL", object()))
def test_registry_rejects_non_policy_values(invalid: object) -> None:
    with pytest.raises(TypeError, match="AmortizedCostPolicy"):
        AmortizedCostPolicyRegistry((invalid,))  # type: ignore[arg-type]


def test_empty_registry_fails_closed() -> None:
    registry = AmortizedCostPolicyRegistry(())

    assert registry.identities == ()
    with pytest.raises(UnsupportedAmortizedCostPolicyError):
        registry.resolve(policy_id="IFRS9_EIR_LOCAL", policy_version=1)
