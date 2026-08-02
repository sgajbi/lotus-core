"""Materialize immutable lot amortized-cost profiles from persisted authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)

from ...domain.fixed_income_book_cost import (
    AmortizedCostEligibilityReason,
    AmortizedCostInputResolutionError,
    AmortizedCostPolicy,
    AmortizedCostReconciliationError,
    LotBookCostAuthorityScope,
    materialize_active_lot_amortized_cost_profile,
    materialize_parked_lot_amortized_cost_profile,
    resolve_lot_amortized_cost_inputs,
)
from ...ports import (
    LotAmortizedCostAuthorityBundle,
    LotAmortizedCostAuthorityPort,
    LotAmortizedCostProfileAppendOutcome,
    LotAmortizedCostProfileHead,
    LotAmortizedCostProfilePort,
)


@dataclass(frozen=True, slots=True)
class LotAmortizedCostMaterializationResult:
    """Minimal durable evidence for one materialization decision."""

    outcome: LotAmortizedCostProfileAppendOutcome
    profile_id: str
    profile_version: int
    authority_content_hash: str
    eligibility_reason: AmortizedCostEligibilityReason | None


class MaterializeLotAmortizedCostProfileUseCase:
    """Resolve source authority and append one active or parked profile version."""

    def __init__(
        self,
        *,
        authority: LotAmortizedCostAuthorityPort,
        profiles: LotAmortizedCostProfilePort,
    ) -> None:
        self._authority = authority
        self._profiles = profiles

    async def execute(
        self,
        *,
        scope: LotBookCostAuthorityScope,
        effective_date: date,
        policy: AmortizedCostPolicy,
        freshness_cutoff: datetime | None = None,
    ) -> LotAmortizedCostMaterializationResult:
        """Reload authority under the profile lock and append only changed evidence."""

        await self._profiles.acquire_materialization_lock(scope)
        bundle = await self._authority.load(scope)
        head = await self._profiles.latest_verified_head(scope)
        next_version = 1 if head is None else head.profile_version + 1
        try:
            resolved = resolve_lot_amortized_cost_inputs(
                assignments=list(bundle.assignments),
                basis_facts=list(bundle.basis_facts),
                schedule_facts=list(bundle.schedule_facts),
                yield_facts=list(bundle.yield_facts),
                scope=scope,
                effective_date=effective_date,
                policy=policy,
                freshness_cutoff=freshness_cutoff,
            )
        except AmortizedCostInputResolutionError as exc:
            return await self._persist_parked_decision(
                bundle,
                head=head,
                scope=scope,
                effective_date=effective_date,
                policy=policy,
                profile_version=next_version,
                reason=exc.reason,
                freshness_cutoff=freshness_cutoff,
            )
        else:
            authority_hash = _active_decision_content_hash(
                resolved.cache_key.authority_content_hash,
                freshness_cutoff=freshness_cutoff,
            )
            if head is not None and head.authority_content_hash == authority_hash:
                return _unchanged_result(
                    head.profile_id,
                    head.profile_version,
                    authority_hash,
                    eligibility_reason=None,
                )
            try:
                profile = materialize_active_lot_amortized_cost_profile(
                    resolved,
                    profile_version=next_version,
                    authority_content_hash=authority_hash,
                )
            except AmortizedCostReconciliationError:
                return await self._persist_parked_decision(
                    bundle,
                    head=head,
                    scope=scope,
                    effective_date=effective_date,
                    policy=policy,
                    profile_version=next_version,
                    reason=AmortizedCostEligibilityReason.RESIDUAL_OUTSIDE_TOLERANCE,
                    freshness_cutoff=freshness_cutoff,
                )
        outcome = await self._profiles.append(profile)
        return LotAmortizedCostMaterializationResult(
            outcome=outcome,
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            authority_content_hash=cast(str, profile.authority_content_hash),
            eligibility_reason=profile.eligibility_reason,
        )

    async def _persist_parked_decision(
        self,
        bundle: LotAmortizedCostAuthorityBundle,
        *,
        head: LotAmortizedCostProfileHead | None,
        scope: LotBookCostAuthorityScope,
        effective_date: date,
        policy: AmortizedCostPolicy,
        profile_version: int,
        reason: AmortizedCostEligibilityReason,
        freshness_cutoff: datetime | None,
    ) -> LotAmortizedCostMaterializationResult:
        """Append or reuse durable fail-closed evidence for one authority decision."""

        authority_hash = _parked_decision_content_hash(
            bundle,
            effective_date=effective_date,
            policy=policy,
            eligibility_reason=reason,
            freshness_cutoff=freshness_cutoff,
        )
        if head is not None and head.authority_content_hash == authority_hash:
            return _unchanged_result(
                head.profile_id,
                head.profile_version,
                authority_hash,
                eligibility_reason=reason,
            )
        profile = materialize_parked_lot_amortized_cost_profile(
            scope=scope,
            effective_date=effective_date,
            profile_version=profile_version,
            reason=reason,
            authority_content_hash=authority_hash,
            source_references=_bundle_source_references(bundle),
        )
        outcome = await self._profiles.append(profile)
        return LotAmortizedCostMaterializationResult(
            outcome=outcome,
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            authority_content_hash=authority_hash,
            eligibility_reason=reason,
        )


def _unchanged_result(
    profile_id: str,
    profile_version: int,
    authority_content_hash: str,
    *,
    eligibility_reason: AmortizedCostEligibilityReason | None,
) -> LotAmortizedCostMaterializationResult:
    return LotAmortizedCostMaterializationResult(
        outcome=LotAmortizedCostProfileAppendOutcome.UNCHANGED,
        profile_id=profile_id,
        profile_version=profile_version,
        authority_content_hash=authority_content_hash,
        eligibility_reason=eligibility_reason,
    )


def _bundle_content_hash(
    bundle: LotAmortizedCostAuthorityBundle,
    *,
    effective_date: date,
) -> str:
    return cast(
        str,
        canonical_content_hash(
            {
                "assignments": sorted(item.content_hash() for item in bundle.assignments),
                "basis_facts": sorted(item.content_hash() for item in bundle.basis_facts),
                "effective_date": effective_date,
                "schedule_facts": sorted(item.content_hash() for item in bundle.schedule_facts),
                "yield_facts": sorted(item.content_hash() for item in bundle.yield_facts),
            }
        ),
    )


def _active_decision_content_hash(
    authority_content_hash: str,
    *,
    freshness_cutoff: datetime | None,
) -> str:
    """Bind freshness policy to active evidence while preserving no-cutoff compatibility."""

    if freshness_cutoff is None:
        return authority_content_hash
    return cast(
        str,
        canonical_content_hash(
            {
                "authority_content_hash": authority_content_hash,
                "freshness_cutoff": freshness_cutoff.astimezone(UTC),
            }
        ),
    )


def _parked_decision_content_hash(
    bundle: LotAmortizedCostAuthorityBundle,
    *,
    effective_date: date,
    policy: AmortizedCostPolicy,
    eligibility_reason: AmortizedCostEligibilityReason,
    freshness_cutoff: datetime | None,
) -> str:
    """Identify the source, policy, and fail-closed decision persisted by a parked profile."""

    return cast(
        str,
        canonical_content_hash(
            {
                "authority_content_hash": _bundle_content_hash(
                    bundle,
                    effective_date=effective_date,
                ),
                "eligibility_reason": eligibility_reason,
                "freshness_cutoff": (
                    freshness_cutoff.astimezone(UTC) if freshness_cutoff is not None else None
                ),
                "policy": {
                    "include_fees_in_amortized_cost": policy.include_fees_in_amortized_cost,
                    "method": policy.method,
                    "policy_id": policy.policy_id,
                    "policy_version": policy.policy_version,
                    "residual_tolerance_local": policy.residual_tolerance_local,
                    "yield_application_convention": policy.yield_application_convention,
                },
            }
        ),
    )


def _bundle_source_references(
    bundle: LotAmortizedCostAuthorityBundle,
) -> tuple[FinancialSourceReference, ...]:
    references = [item.source_reference() for item in bundle.assignments]
    references.extend(item.source_reference() for item in bundle.basis_facts)
    references.extend(item.source_reference() for item in bundle.schedule_facts)
    references.extend(item.source_reference() for item in bundle.yield_facts)
    return tuple(
        sorted(
            references,
            key=lambda item: (
                item.source_system,
                item.source_record_id,
                item.source_revision,
                item.source_content_hash,
            ),
        )
    )
