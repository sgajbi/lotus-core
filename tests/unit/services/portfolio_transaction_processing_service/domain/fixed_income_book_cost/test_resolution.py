"""Tests for fail-closed lot amortized-cost source-bundle resolution."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizationPeriodInput,
    AmortizedCostAssignmentStatus,
    AmortizedCostEligibilityReason,
    AmortizedCostInputResolutionError,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    AmortizedCostSourceFactStatus,
    AmortizedCostSourceMetadata,
    DiscountOriginClassification,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    LotEffectiveYieldFact,
    YieldApplicationConvention,
    resolve_lot_amortized_cost_inputs,
)

AS_OF = date(2026, 7, 18)


def _scope(**overrides: str) -> LotBookCostAuthorityScope:
    values = {
        "tenant_id": "TENANT_SG",
        "legal_book_id": "BOOK_SG_PB",
        "portfolio_id": "PORTFOLIO_001",
        "security_id": "SEC_BOND_001",
        "lot_id": "LOT_BUY_001",
    }
    values.update(overrides)
    return LotBookCostAuthorityScope(**values)


def _source(record_id: str, **overrides: object) -> AmortizedCostSourceMetadata:
    values: dict[str, object] = {
        "source_system": "fixed_income_accounting_master",
        "source_record_id": record_id,
        "source_revision": "revision-1",
        "fact_version": 1,
        "observed_at": datetime(2026, 7, 18, 8, tzinfo=UTC),
    }
    values.update(overrides)
    return AmortizedCostSourceMetadata(**values)  # type: ignore[arg-type]


def _policy(
    *,
    method: AmortizedCostMethod = AmortizedCostMethod.EFFECTIVE_YIELD,
    convention: YieldApplicationConvention | None = (
        YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE
    ),
) -> AmortizedCostPolicy:
    return AmortizedCostPolicy(
        policy_id="IFRS9_EIR_LOCAL",
        policy_version=2,
        method=method,
        yield_application_convention=convention,
        include_fees_in_amortized_cost=True,
        residual_tolerance_local=Decimal("0.0000000001"),
    )


def _assignment(**overrides: object) -> LotAmortizedCostPolicyAssignment:
    values: dict[str, object] = {
        "scope": _scope(),
        "policy_id": "IFRS9_EIR_LOCAL",
        "policy_version": 2,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "assignment_status": AmortizedCostAssignmentStatus.ACTIVE,
        "assignment_version": 1,
        "source_system": "accounting_policy_master",
        "source_record_id": "LOT_BUY_001_POLICY",
        "source_revision": "revision-1",
        "observed_at": datetime(2026, 7, 18, 8, tzinfo=UTC),
        "assignment_reason": "Approved treatment",
    }
    values.update(overrides)
    return LotAmortizedCostPolicyAssignment(**values)  # type: ignore[arg-type]


def _basis(**overrides: object) -> LotAmortizedCostBasisFact:
    values: dict[str, object] = {
        "scope": _scope(),
        "currency": "SGD",
        "initial_clean_cost_local": Decimal("97"),
        "fees_in_basis_local": Decimal("0"),
        "redemption_value_local": Decimal("100"),
        "discount_origin": DiscountOriginClassification.MARKET_DISCOUNT,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "fact_status": AmortizedCostSourceFactStatus.ACTIVE,
        "source": _source("LOT_BUY_001_BASIS"),
    }
    values.update(overrides)
    return LotAmortizedCostBasisFact(**values)  # type: ignore[arg-type]


def _schedule(**overrides: object) -> LotAmortizationScheduleFact:
    values: dict[str, object] = {
        "scope": _scope(),
        "schedule_version": 1,
        "year_fraction_method_id": "ACTUAL_ACTUAL_ICMA",
        "year_fraction_method_version": 1,
        "periods": (
            AmortizationPeriodInput(
                period_start_date=date(2026, 1, 1),
                period_end_date=date(2027, 1, 1),
                year_fraction=Decimal("1"),
                cash_coupon_local=Decimal("2"),
            ),
        ),
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "fact_status": AmortizedCostSourceFactStatus.ACTIVE,
        "source": _source("SEC_BOND_001_SCHEDULE"),
    }
    values.update(overrides)
    return LotAmortizationScheduleFact(**values)  # type: ignore[arg-type]


def _yield(**overrides: object) -> LotEffectiveYieldFact:
    values: dict[str, object] = {
        "scope": _scope(),
        "annual_yield": Decimal("0.05154639175257731958762886598"),
        "yield_application_convention": YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "fact_status": AmortizedCostSourceFactStatus.ACTIVE,
        "source": _source("LOT_BUY_001_EIR"),
    }
    values.update(overrides)
    return LotEffectiveYieldFact(**values)  # type: ignore[arg-type]


def _resolve(**overrides: object):  # type: ignore[no-untyped-def]
    values: dict[str, object] = {
        "assignments": [_assignment()],
        "basis_facts": [_basis()],
        "schedule_facts": [_schedule()],
        "yield_facts": [_yield()],
        "scope": _scope(),
        "effective_date": AS_OF,
        "policy": _policy(),
    }
    values.update(overrides)
    return resolve_lot_amortized_cost_inputs(**values)  # type: ignore[arg-type]


def test_resolution_builds_complete_calculation_inputs_and_cache_identity() -> None:
    resolved = _resolve()

    assert resolved.calculation_inputs.initial_clean_cost_local == Decimal("97")
    assert resolved.calculation_inputs.annual_yield == _yield().annual_yield
    assert resolved.calculation_inputs.periods == _schedule().periods
    assert len(resolved.source_references) == 4
    assert resolved.cache_key.scope == _scope()
    assert resolved.cache_key.policy_version == 2
    assert len(resolved.cache_key.authority_content_hash) == 64


def test_resolution_never_uses_facts_from_a_different_lot_scope() -> None:
    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(basis_facts=[_basis(scope=_scope(lot_id="LOT_OTHER"))])

    assert caught.value.reason is AmortizedCostEligibilityReason.CLEAN_COST_EVIDENCE_MISSING


@pytest.mark.parametrize(
    ("field_name", "facts_name", "reason"),
    [
        (
            "basis_facts",
            "clean-cost basis",
            AmortizedCostEligibilityReason.SOURCE_FACT_OVERLAPPING,
        ),
        (
            "schedule_facts",
            "amortization schedule",
            AmortizedCostEligibilityReason.SOURCE_FACT_OVERLAPPING,
        ),
        (
            "yield_facts",
            "effective-yield",
            AmortizedCostEligibilityReason.SOURCE_FACT_OVERLAPPING,
        ),
    ],
)
def test_distinct_overlapping_source_records_fail_closed(
    field_name: str,
    facts_name: str,
    reason: AmortizedCostEligibilityReason,
) -> None:
    first = {"basis_facts": _basis, "schedule_facts": _schedule, "yield_facts": _yield}[
        field_name
    ]()
    second = replace(
        first,
        source=replace(first.source, source_record_id=f"SECOND_{field_name.upper()}"),
    )
    with pytest.raises(AmortizedCostInputResolutionError, match=facts_name) as caught:
        _resolve(**{field_name: [first, second]})

    assert caught.value.reason is reason


def test_later_suspended_fact_version_fences_older_active_fact() -> None:
    active = _basis()
    suspended = replace(
        active,
        fact_status=AmortizedCostSourceFactStatus.SUSPENDED,
        source=replace(active.source, fact_version=2, source_revision="revision-2"),
    )

    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(basis_facts=[active, suspended])

    assert caught.value.reason is AmortizedCostEligibilityReason.CLEAN_COST_EVIDENCE_MISSING


def test_conflicting_same_source_version_has_stable_reason() -> None:
    first = _basis()
    conflicting = replace(first, redemption_value_local=Decimal("101"))

    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(basis_facts=[first, conflicting])

    assert caught.value.reason is AmortizedCostEligibilityReason.SOURCE_FACT_CONFLICTING


@pytest.mark.parametrize("newest_first", [False, True])
def test_conflicting_older_source_version_fails_closed_independent_of_order(
    newest_first: bool,
) -> None:
    first = _basis()
    conflicting = replace(first, redemption_value_local=Decimal("101"))
    corrected = replace(
        first,
        redemption_value_local=Decimal("102"),
        source=replace(first.source, fact_version=2, source_revision="revision-2"),
    )
    facts = [corrected, first, conflicting] if newest_first else [first, conflicting, corrected]

    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(basis_facts=facts)

    assert caught.value.reason is AmortizedCostEligibilityReason.SOURCE_FACT_CONFLICTING


def test_conflicting_assignment_source_version_has_distinct_stable_reason() -> None:
    first = _assignment()
    conflicting = replace(first, policy_version=3)

    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(assignments=[first, conflicting])

    assert caught.value.reason is AmortizedCostEligibilityReason.ASSIGNMENT_CONFLICTING


def test_missing_annual_yield_has_stable_reason() -> None:
    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(yield_facts=[])

    assert caught.value.reason is AmortizedCostEligibilityReason.EFFECTIVE_YIELD_MISSING


def test_yield_convention_mismatch_fails_closed() -> None:
    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(
            yield_facts=[
                _yield(yield_application_convention=YieldApplicationConvention.ANNUAL_EFFECTIVE)
            ]
        )

    assert caught.value.reason is AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH


def test_per_period_policy_resolves_without_annual_yield_fact() -> None:
    schedule = _schedule(
        periods=(replace(_schedule().periods[0], supplied_period_rate=Decimal("0.05")),)
    )
    resolved = _resolve(
        policy=_policy(convention=YieldApplicationConvention.PER_PERIOD_EFFECTIVE),
        schedule_facts=[schedule],
        yield_facts=[],
    )

    assert resolved.yield_fact is None
    assert resolved.calculation_inputs.annual_yield is None
    assert resolved.calculation_inputs.periods[0].supplied_period_rate == Decimal("0.05")


def test_per_period_policy_requires_every_authoritative_period_rate() -> None:
    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(
            policy=_policy(convention=YieldApplicationConvention.PER_PERIOD_EFFECTIVE),
            yield_facts=[],
        )

    assert caught.value.reason is AmortizedCostEligibilityReason.PERIOD_RATE_MISSING


def test_annual_yield_policy_rejects_schedule_owned_period_rates() -> None:
    schedule = _schedule(
        periods=(replace(_schedule().periods[0], supplied_period_rate=Decimal("0.05")),)
    )

    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(schedule_facts=[schedule])

    assert caught.value.reason is AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH


def test_straight_line_policy_rejects_undeclared_yield_authority() -> None:
    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(
            policy=_policy(
                method=AmortizedCostMethod.STRAIGHT_LINE,
                convention=None,
            )
        )

    assert caught.value.reason is AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH


def test_suspended_yield_fact_does_not_block_straight_line_authority() -> None:
    suspended = replace(
        _yield(),
        fact_status=AmortizedCostSourceFactStatus.SUSPENDED,
    )

    resolved = _resolve(
        policy=_policy(
            method=AmortizedCostMethod.STRAIGHT_LINE,
            convention=None,
        ),
        yield_facts=[suspended],
    )

    assert resolved.yield_fact is None


def test_policy_identity_must_match_exact_assignment() -> None:
    mismatched = replace(_policy(), policy_version=3)

    with pytest.raises(AmortizedCostInputResolutionError) as caught:
        _resolve(policy=mismatched)

    assert caught.value.reason is AmortizedCostEligibilityReason.POLICY_IDENTITY_MISMATCH


def test_freshness_cutoff_fails_closed_with_stable_reason() -> None:
    with pytest.raises(AmortizedCostInputResolutionError, match="stale") as caught:
        _resolve(freshness_cutoff=datetime(2026, 7, 19, tzinfo=UTC))

    assert caught.value.reason is AmortizedCostEligibilityReason.AUTHORITY_STALE


def test_source_correction_invalidates_authority_cache_identity() -> None:
    baseline = _resolve()
    corrected_basis = replace(
        _basis(),
        source=replace(_basis().source, fact_version=2, source_revision="revision-2"),
    )
    corrected = _resolve(basis_facts=[_basis(), corrected_basis])

    assert baseline.cache_key.authority_content_hash != corrected.cache_key.authority_content_hash
    assert baseline.cache_key.basis_content_hash != corrected.cache_key.basis_content_hash
