"""Tests for immutable active and parked amortized-cost profile materialization."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizationPeriodInput,
    AmortizedCostAssignmentStatus,
    AmortizedCostEligibilityReason,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    AmortizedCostProfileStatus,
    AmortizedCostSourceFactStatus,
    AmortizedCostSourceMetadata,
    DiscountOriginClassification,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    LotEffectiveYieldFact,
    YieldApplicationConvention,
    lot_amortized_cost_profile_id,
    materialize_active_lot_amortized_cost_profile,
    materialize_parked_lot_amortized_cost_profile,
    resolve_lot_amortized_cost_inputs,
)


def _scope() -> LotBookCostAuthorityScope:
    return LotBookCostAuthorityScope(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="SEC_BOND_001",
        lot_id="LOT_BUY_001",
    )


def _source(record_id: str) -> AmortizedCostSourceMetadata:
    return AmortizedCostSourceMetadata(
        source_system="fixed_income_accounting_master",
        source_record_id=record_id,
        source_revision="revision-1",
        fact_version=1,
        observed_at=datetime(2026, 1, 1, 8, tzinfo=UTC),
    )


def _resolved():  # type: ignore[no-untyped-def]
    scope = _scope()
    policy = AmortizedCostPolicy(
        policy_id="IFRS9_EIR_LOCAL",
        policy_version=1,
        method=AmortizedCostMethod.EFFECTIVE_YIELD,
        yield_application_convention=YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
        include_fees_in_amortized_cost=True,
        residual_tolerance_local=Decimal("0.0000000001"),
    )
    return resolve_lot_amortized_cost_inputs(
        assignments=[
            LotAmortizedCostPolicyAssignment(
                scope=scope,
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                valid_from=date(2026, 1, 1),
                valid_to=None,
                assignment_status=AmortizedCostAssignmentStatus.ACTIVE,
                assignment_version=1,
                source_system="accounting_policy_master",
                source_record_id="LOT_BUY_001_POLICY",
                source_revision="revision-1",
                observed_at=datetime(2026, 1, 1, 8, tzinfo=UTC),
                assignment_reason="Approved treatment",
            )
        ],
        basis_facts=[
            LotAmortizedCostBasisFact(
                scope=scope,
                currency="SGD",
                initial_clean_cost_local=Decimal("97"),
                fees_in_basis_local=Decimal("0"),
                redemption_value_local=Decimal("100"),
                discount_origin=DiscountOriginClassification.MARKET_DISCOUNT,
                valid_from=date(2026, 1, 1),
                valid_to=None,
                fact_status=AmortizedCostSourceFactStatus.ACTIVE,
                source=_source("LOT_BUY_001_BASIS"),
            )
        ],
        schedule_facts=[
            LotAmortizationScheduleFact(
                scope=scope,
                schedule_version=2,
                year_fraction_method_id="ACTUAL_ACTUAL_ICMA",
                year_fraction_method_version=1,
                periods=(
                    AmortizationPeriodInput(
                        period_start_date=date(2026, 1, 1),
                        period_end_date=date(2027, 1, 1),
                        year_fraction=Decimal("1"),
                        cash_coupon_local=Decimal("2"),
                    ),
                ),
                valid_from=date(2026, 1, 1),
                valid_to=None,
                fact_status=AmortizedCostSourceFactStatus.ACTIVE,
                source=_source("SEC_BOND_001_SCHEDULE"),
            )
        ],
        yield_facts=[
            LotEffectiveYieldFact(
                scope=scope,
                annual_yield=Decimal("0.05154639175257731958762886598"),
                yield_application_convention=(YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE),
                valid_from=date(2026, 1, 1),
                valid_to=None,
                fact_status=AmortizedCostSourceFactStatus.ACTIVE,
                source=_source("LOT_BUY_001_EIR"),
            )
        ],
        scope=scope,
        effective_date=date(2026, 1, 1),
        policy=policy,
    )


def test_active_profile_materializes_reconciled_period_ledger_and_lineage() -> None:
    profile = materialize_active_lot_amortized_cost_profile(
        _resolved(),
        profile_version=1,
    )

    assert profile.status is AmortizedCostProfileStatus.ACTIVE
    assert profile.eligibility_reason is None
    assert profile.profile_id == lot_amortized_cost_profile_id(_scope())
    assert profile.schedule_version == 2
    assert profile.currency == "SGD"
    assert profile.initial_amortized_cost_local == Decimal("97.0000000000")
    assert profile.final_amortized_cost_local == Decimal("100.0000000000")
    assert profile.residual_local == Decimal("0E-10")
    assert all(
        value.as_tuple().exponent == -10
        for value in (
            profile.initial_amortized_cost_local,
            profile.redemption_value_local,
            profile.final_amortized_cost_local,
            profile.residual_local,
            profile.periods[0].begin_amortized_cost_local,
            profile.periods[0].interest_income_local,
            profile.periods[0].cash_coupon_local,
            profile.periods[0].amortization_amount_local,
            profile.periods[0].end_amortized_cost_local,
            profile.periods[0].rounding_adjustment_local,
        )
    )
    assert len(profile.source_references) == 4
    assert len(profile.periods) == 1
    period = profile.periods[0]
    assert period.period_ordinal == 1
    assert period.profile_id == profile.profile_id
    assert period.profile_version == profile.profile_version
    assert period.calculation_output_hash == profile.calculation_lineage.output_content_hash
    assert len(period.content_hash()) == 64
    assert len(profile.content_hash()) == 64


def test_exact_replay_materializes_identical_profile_and_period_hashes() -> None:
    resolved = _resolved()

    first = materialize_active_lot_amortized_cost_profile(resolved, profile_version=1)
    replay = materialize_active_lot_amortized_cost_profile(resolved, profile_version=1)

    assert first == replay
    assert first.content_hash() == replay.content_hash()


def test_profile_version_changes_append_identity_without_changing_stable_profile_id() -> None:
    resolved = _resolved()

    first = materialize_active_lot_amortized_cost_profile(resolved, profile_version=1)
    corrected = materialize_active_lot_amortized_cost_profile(resolved, profile_version=2)

    assert first.profile_id == corrected.profile_id
    assert first.profile_version == 1
    assert corrected.profile_version == 2
    assert first.content_hash() != corrected.content_hash()


def test_parked_profile_preserves_reason_without_inventing_economics() -> None:
    profile = materialize_parked_lot_amortized_cost_profile(
        scope=_scope(),
        effective_date=date(2026, 1, 1),
        profile_version=1,
        reason=AmortizedCostEligibilityReason.CASHFLOW_SCHEDULE_MISSING,
    )

    assert profile.status is AmortizedCostProfileStatus.PARKED
    assert profile.eligibility_reason is (AmortizedCostEligibilityReason.CASHFLOW_SCHEDULE_MISSING)
    assert profile.periods == ()
    assert profile.calculation_lineage is None
    assert profile.initial_amortized_cost_local is None
    assert len(profile.content_hash()) == 64


def test_active_profile_rejects_periods_not_bound_to_calculation_output() -> None:
    profile = materialize_active_lot_amortized_cost_profile(
        _resolved(),
        profile_version=1,
    )
    invalid_period = replace(profile.periods[0], calculation_output_hash="0" * 64)

    with pytest.raises(ValueError, match="bind the profile calculation output hash"):
        replace(profile, periods=(invalid_period,))


def test_active_profile_rejects_tampered_period_economics_with_unchanged_lineage() -> None:
    profile = materialize_active_lot_amortized_cost_profile(
        _resolved(),
        profile_version=1,
    )
    tampered_period = replace(
        profile.periods[0],
        interest_income_local=Decimal("999"),
    )

    with pytest.raises(ValueError, match="do not match calculation lineage"):
        replace(profile, periods=(tampered_period,))


def test_nonactive_profile_rejects_calculated_economics() -> None:
    parked = materialize_parked_lot_amortized_cost_profile(
        scope=_scope(),
        effective_date=date(2026, 1, 1),
        profile_version=1,
        reason=AmortizedCostEligibilityReason.AUTHORITY_STALE,
    )

    with pytest.raises(ValueError, match="must not contain final_amortized_cost_local"):
        replace(parked, final_amortized_cost_local=Decimal("100"))


@pytest.mark.parametrize("profile_version", [0, -1, True, Decimal("1")])
def test_profile_version_must_be_a_positive_integer(profile_version: object) -> None:
    with pytest.raises((TypeError, ValueError), match="profile_version"):
        materialize_active_lot_amortized_cost_profile(
            _resolved(),
            profile_version=profile_version,  # type: ignore[arg-type]
        )


def test_new_profile_materialization_rejects_terminal_lifecycle_status() -> None:
    active = materialize_active_lot_amortized_cost_profile(
        _resolved(),
        profile_version=1,
    )

    with pytest.raises(ValueError, match="must be ACTIVE, PARKED, or INELIGIBLE"):
        replace(active, status=AmortizedCostProfileStatus.SUPERSEDED)
