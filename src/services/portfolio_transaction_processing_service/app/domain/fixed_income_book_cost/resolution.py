"""Fail-closed resolution of complete lot amortized-cost calculation authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TypeVar, cast

from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)
from portfolio_common.domain.source_versions import latest_source_versions

from .authority import (
    AmortizedCostAuthorityError,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    MissingAmortizedCostAssignmentError,
    OverlappingAmortizedCostAssignmentError,
    ResolvedAmortizedCostAssignment,
    resolve_amortized_cost_assignment,
)
from .calculation import AmortizedCostScheduleInput
from .policy import (
    AmortizedCostEligibilityReason,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    YieldApplicationConvention,
)
from .source_facts import (
    AmortizedCostSourceFactStatus,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotEffectiveYieldFact,
)


class AmortizedCostInputResolutionError(ValueError):
    """Fail-closed resolution error carrying a stable parked-profile reason."""

    def __init__(self, reason: AmortizedCostEligibilityReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class LotAmortizedCostAuthorityCacheKey:
    """Complete source identity for safe resolved-input caching and invalidation."""

    scope: LotBookCostAuthorityScope
    effective_date: date
    policy_id: str
    policy_version: int
    assignment_content_hash: str
    basis_content_hash: str
    schedule_content_hash: str
    yield_content_hash: str | None
    authority_content_hash: str


@dataclass(frozen=True, slots=True)
class ResolvedLotAmortizedCostInputs:
    """Complete calculation inputs plus source evidence and cache identity."""

    assignment: LotAmortizedCostPolicyAssignment
    policy: AmortizedCostPolicy
    basis_fact: LotAmortizedCostBasisFact
    schedule_fact: LotAmortizationScheduleFact
    yield_fact: LotEffectiveYieldFact | None
    calculation_inputs: AmortizedCostScheduleInput
    source_references: tuple[FinancialSourceReference, ...]
    cache_key: LotAmortizedCostAuthorityCacheKey


_FactT = TypeVar(
    "_FactT",
    LotAmortizedCostBasisFact,
    LotAmortizationScheduleFact,
    LotEffectiveYieldFact,
)


def resolve_lot_amortized_cost_inputs(
    *,
    assignments: list[LotAmortizedCostPolicyAssignment],
    basis_facts: list[LotAmortizedCostBasisFact],
    schedule_facts: list[LotAmortizationScheduleFact],
    yield_facts: list[LotEffectiveYieldFact],
    scope: LotBookCostAuthorityScope,
    effective_date: date,
    policy: AmortizedCostPolicy,
    freshness_cutoff: datetime | None = None,
) -> ResolvedLotAmortizedCostInputs:
    """Resolve one complete exact-scope bundle or return a stable failure reason."""

    _validate_request(scope, effective_date, policy, freshness_cutoff)
    assignment = _resolve_assignment(assignments, scope, effective_date)
    _validate_policy_identity(assignment, policy)
    basis = _resolve_fact(
        basis_facts,
        scope=scope,
        effective_date=effective_date,
        missing_reason=AmortizedCostEligibilityReason.CLEAN_COST_EVIDENCE_MISSING,
        fact_name="clean-cost basis",
    )
    schedule = _resolve_fact(
        schedule_facts,
        scope=scope,
        effective_date=effective_date,
        missing_reason=AmortizedCostEligibilityReason.CASHFLOW_SCHEDULE_MISSING,
        fact_name="amortization schedule",
    )
    _validate_schedule_rate_authority(policy, schedule)
    _validate_freshness(
        (assignment.assignment, basis, schedule),
        freshness_cutoff=freshness_cutoff,
    )
    yield_fact = _resolve_yield_fact(
        yield_facts,
        scope=scope,
        effective_date=effective_date,
        policy=policy,
    )
    if yield_fact is not None:
        _validate_freshness((yield_fact,), freshness_cutoff=freshness_cutoff)
    calculation_inputs = AmortizedCostScheduleInput(
        initial_clean_cost_local=basis.initial_clean_cost_local,
        fees_in_basis_local=basis.fees_in_basis_local,
        redemption_value_local=basis.redemption_value_local,
        periods=schedule.periods,
        annual_yield=yield_fact.annual_yield if yield_fact is not None else None,
    )
    references = (
        assignment.assignment.source_reference(),
        basis.source_reference(),
        schedule.source_reference(),
        *((yield_fact.source_reference(),) if yield_fact is not None else ()),
    )
    cache_key = _cache_key(
        scope=scope,
        effective_date=effective_date,
        assignment=assignment,
        basis=basis,
        schedule=schedule,
        yield_fact=yield_fact,
        policy=policy,
    )
    return ResolvedLotAmortizedCostInputs(
        assignment=assignment.assignment,
        policy=policy,
        basis_fact=basis,
        schedule_fact=schedule,
        yield_fact=yield_fact,
        calculation_inputs=calculation_inputs,
        source_references=references,
        cache_key=cache_key,
    )


def _resolve_assignment(
    assignments: list[LotAmortizedCostPolicyAssignment],
    scope: LotBookCostAuthorityScope,
    effective_date: date,
) -> ResolvedAmortizedCostAssignment:
    try:
        return resolve_amortized_cost_assignment(
            assignments,
            scope=scope,
            effective_date=effective_date,
        )
    except MissingAmortizedCostAssignmentError as exc:
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.ASSIGNMENT_MISSING,
            str(exc),
        ) from exc
    except OverlappingAmortizedCostAssignmentError as exc:
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.ASSIGNMENT_OVERLAPPING,
            str(exc),
        ) from exc
    except AmortizedCostAuthorityError as exc:
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.ASSIGNMENT_CONFLICTING,
            str(exc),
        ) from exc


def _resolve_fact(
    facts: list[_FactT],
    *,
    scope: LotBookCostAuthorityScope,
    effective_date: date,
    missing_reason: AmortizedCostEligibilityReason,
    fact_name: str,
) -> _FactT:
    effective = _active_effective_facts(
        facts,
        scope=scope,
        effective_date=effective_date,
        fact_name=fact_name,
    )
    if not effective:
        raise AmortizedCostInputResolutionError(
            missing_reason,
            f"no active {fact_name} fact for exact source-lot scope and date",
        )
    if len(effective) > 1:
        sources = sorted(
            f"{fact.source.source_system}:{fact.source.source_record_id}" for fact in effective
        )
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.SOURCE_FACT_OVERLAPPING,
            f"overlapping active {fact_name} facts: {sources}",
        )
    return effective[0]


def _active_effective_facts(
    facts: list[_FactT],
    *,
    scope: LotBookCostAuthorityScope,
    effective_date: date,
    fact_name: str,
) -> list[_FactT]:
    scoped = [fact for fact in facts if fact.scope == scope]
    try:
        latest = cast(
            list[_FactT],
            latest_source_versions(
                scoped,
                source_record_key=lambda fact: fact.source_record_key,
                source_version=lambda fact: fact.source.fact_version,
                conflicting_version_error=lambda: AmortizedCostInputResolutionError(
                    AmortizedCostEligibilityReason.SOURCE_FACT_CONFLICTING,
                    f"conflicting {fact_name} payloads share one source version",
                ),
            ),
        )
    except AmortizedCostInputResolutionError:
        raise
    return [
        fact
        for fact in latest
        if fact.fact_status is AmortizedCostSourceFactStatus.ACTIVE
        and fact.is_effective_on(effective_date)
    ]


def _resolve_yield_fact(
    yield_facts: list[LotEffectiveYieldFact],
    *,
    scope: LotBookCostAuthorityScope,
    effective_date: date,
    policy: AmortizedCostPolicy,
) -> LotEffectiveYieldFact | None:
    effective_candidates = _active_effective_facts(
        yield_facts,
        scope=scope,
        effective_date=effective_date,
        fact_name="effective-yield",
    )
    if policy.method is AmortizedCostMethod.STRAIGHT_LINE:
        if effective_candidates:
            raise AmortizedCostInputResolutionError(
                AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH,
                "straight-line authority must not include a yield fact",
            )
        return None
    if policy.yield_application_convention is YieldApplicationConvention.PER_PERIOD_EFFECTIVE:
        if effective_candidates:
            raise AmortizedCostInputResolutionError(
                AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH,
                "per-period-effective authority must not include an annual yield fact",
            )
        return None
    fact = _resolve_fact(
        yield_facts,
        scope=scope,
        effective_date=effective_date,
        missing_reason=AmortizedCostEligibilityReason.EFFECTIVE_YIELD_MISSING,
        fact_name="effective-yield",
    )
    if fact.yield_application_convention is not policy.yield_application_convention:
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH,
            "yield fact convention does not match the assigned amortized-cost policy",
        )
    return fact


def _validate_schedule_rate_authority(
    policy: AmortizedCostPolicy,
    schedule: LotAmortizationScheduleFact,
) -> None:
    supplied_rates = tuple(period.supplied_period_rate for period in schedule.periods)
    if policy.method is AmortizedCostMethod.STRAIGHT_LINE:
        if any(rate is not None for rate in supplied_rates):
            raise AmortizedCostInputResolutionError(
                AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH,
                "straight-line authority must not include supplied period rates",
            )
        return
    if policy.yield_application_convention is YieldApplicationConvention.PER_PERIOD_EFFECTIVE:
        if any(rate is None for rate in supplied_rates):
            raise AmortizedCostInputResolutionError(
                AmortizedCostEligibilityReason.PERIOD_RATE_MISSING,
                "each per-period-effective schedule period requires a supplied rate",
            )
        return
    if any(rate is not None for rate in supplied_rates):
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.YIELD_CONVENTION_MISMATCH,
            "annual-yield authority must not include supplied period rates",
        )


def _validate_policy_identity(
    assignment: ResolvedAmortizedCostAssignment,
    policy: AmortizedCostPolicy,
) -> None:
    if (
        assignment.assignment.policy_id != policy.policy_id
        or assignment.assignment.policy_version != policy.policy_version
    ):
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.POLICY_IDENTITY_MISMATCH,
            "resolved policy does not match the exact source-lot assignment",
        )


def _validate_freshness(
    records: tuple[object, ...],
    *,
    freshness_cutoff: datetime | None,
) -> None:
    if freshness_cutoff is None:
        return
    stale_sources: list[str] = []
    for record in records:
        if isinstance(record, LotAmortizedCostPolicyAssignment):
            observed_at = record.observed_at
            source_name = f"{record.source_system}:{record.source_record_id}"
        else:
            fact = cast(
                LotAmortizedCostBasisFact | LotAmortizationScheduleFact | LotEffectiveYieldFact,
                record,
            )
            observed_at = fact.source.observed_at
            source_name = f"{fact.source.source_system}:{fact.source.source_record_id}"
        if observed_at < freshness_cutoff:
            stale_sources.append(source_name)
    if stale_sources:
        raise AmortizedCostInputResolutionError(
            AmortizedCostEligibilityReason.AUTHORITY_STALE,
            f"amortized-cost authority is stale: {sorted(stale_sources)}",
        )


def _cache_key(
    *,
    scope: LotBookCostAuthorityScope,
    effective_date: date,
    assignment: ResolvedAmortizedCostAssignment,
    basis: LotAmortizedCostBasisFact,
    schedule: LotAmortizationScheduleFact,
    yield_fact: LotEffectiveYieldFact | None,
    policy: AmortizedCostPolicy,
) -> LotAmortizedCostAuthorityCacheKey:
    yield_hash = yield_fact.content_hash() if yield_fact is not None else None
    authority_hash = canonical_content_hash(
        {
            "assignment_content_hash": assignment.cache_key.assignment_content_hash,
            "basis_content_hash": basis.content_hash(),
            "effective_date": effective_date,
            "policy": {
                "include_fees_in_amortized_cost": policy.include_fees_in_amortized_cost,
                "method": policy.method,
                "policy_id": policy.policy_id,
                "policy_version": policy.policy_version,
                "residual_tolerance_local": policy.residual_tolerance_local,
                "yield_application_convention": policy.yield_application_convention,
            },
            "schedule_content_hash": schedule.content_hash(),
            "scope": scope.key,
            "yield_content_hash": yield_hash,
        }
    )
    return LotAmortizedCostAuthorityCacheKey(
        scope=scope,
        effective_date=effective_date,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        assignment_content_hash=assignment.cache_key.assignment_content_hash,
        basis_content_hash=basis.content_hash(),
        schedule_content_hash=schedule.content_hash(),
        yield_content_hash=yield_hash,
        authority_content_hash=cast(str, authority_hash),
    )


def _validate_request(
    scope: object,
    effective_date: object,
    policy: object,
    freshness_cutoff: object,
) -> None:
    if not isinstance(scope, LotBookCostAuthorityScope):
        raise TypeError("scope must be a LotBookCostAuthorityScope")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date")
    if not isinstance(policy, AmortizedCostPolicy):
        raise TypeError("policy must be an AmortizedCostPolicy")
    if freshness_cutoff is not None:
        if not isinstance(freshness_cutoff, datetime):
            raise TypeError("freshness_cutoff must be a datetime or None")
        if freshness_cutoff.tzinfo is None or freshness_cutoff.utcoffset() is None:
            raise ValueError("freshness_cutoff must be timezone-aware")
