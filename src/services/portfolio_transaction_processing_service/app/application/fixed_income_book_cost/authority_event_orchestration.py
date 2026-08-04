"""Apply one source-owned fixed-income book-cost authority event."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from types import TracebackType
from typing import Protocol, Self

from portfolio_common.event_contracts import FixedIncomeBookCostAuthorityEvent

from ...domain.fixed_income_book_cost import (
    AmortizedCostAuthorityError,
    AmortizedCostEligibilityReason,
    AmortizedCostPolicy,
    AmortizedCostPolicyRegistry,
    FixedIncomeBookCostCorrectionReplayIntent,
    FixedIncomeBookCostProfileDecisionEvidence,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    MissingAmortizedCostAssignmentError,
    OverlappingAmortizedCostAssignmentError,
    UnsupportedAmortizedCostPolicyError,
    amortization_replay_start_for_assignment_correction,
    resolve_amortized_cost_assignment,
)
from ...ports import (
    FixedIncomeBookCostCorrectionReplayPort,
    LotAmortizedCostAuthority,
    LotAmortizedCostAuthorityPort,
    LotAmortizedCostProfileAppendOutcome,
    LotAmortizedCostProfilePort,
)
from .authority_event_mapping import map_fixed_income_book_cost_authority_event
from .authority_writer import (
    PersistLotAmortizedCostAuthorityResult,
    PersistLotAmortizedCostAuthorityUseCase,
)
from .materialization import (
    LotAmortizedCostMaterializationResult,
    MaterializeLotAmortizedCostProfileUseCase,
)


@dataclass(frozen=True, slots=True)
class ApplyFixedIncomeBookCostAuthorityEventResult:
    """Persistence and materialization evidence for one accepted source event."""

    scope: LotBookCostAuthorityScope
    persistence: PersistLotAmortizedCostAuthorityResult
    materialization: LotAmortizedCostMaterializationResult
    rematerializations: tuple[LotAmortizedCostMaterializationResult, ...] = ()
    correction_replay_intent: FixedIncomeBookCostCorrectionReplayIntent | None = None


class FixedIncomeBookCostAuthorityUnitOfWork(Protocol):
    """Atomic persistence boundary required by the authority event handler."""

    @property
    def authority(self) -> LotAmortizedCostAuthorityPort: ...

    @property
    def profiles(self) -> LotAmortizedCostProfilePort: ...

    @property
    def correction_replay(self) -> FixedIncomeBookCostCorrectionReplayPort: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


FixedIncomeBookCostAuthorityUnitOfWorkFactory = Callable[[], FixedIncomeBookCostAuthorityUnitOfWork]


class ApplyFixedIncomeBookCostAuthorityEventUseCase:
    """Persist one mapped authority and materialize its exact source-lot scope.

    The caller owns the transaction boundary. Both reused use cases operate through the supplied
    ports so an authority append and its derived profile can commit or roll back together.
    """

    def __init__(
        self,
        *,
        authority: LotAmortizedCostAuthorityPort,
        profiles: LotAmortizedCostProfilePort,
    ) -> None:
        self._writer = PersistLotAmortizedCostAuthorityUseCase(authority)
        self._materializer = MaterializeLotAmortizedCostProfileUseCase(
            authority=authority,
            profiles=profiles,
        )

    async def execute(
        self,
        event: FixedIncomeBookCostAuthorityEvent,
        *,
        effective_date: date,
        policy: AmortizedCostPolicy,
        freshness_cutoff: datetime | None = None,
    ) -> ApplyFixedIncomeBookCostAuthorityEventResult:
        """Apply explicit policy/date authority without inferring scope or owning commit."""

        mapped = map_fixed_income_book_cost_authority_event(event)
        persistence = await self._writer.execute((mapped,))
        materialization = await self._materializer.execute(
            scope=mapped.scope,
            effective_date=effective_date,
            policy=policy,
            freshness_cutoff=freshness_cutoff,
        )
        return ApplyFixedIncomeBookCostAuthorityEventResult(
            scope=mapped.scope,
            persistence=persistence,
            materialization=materialization,
        )


class HandleFixedIncomeBookCostAuthorityEventUseCase:
    """Apply one event under a single database transaction and explicit policy catalog."""

    def __init__(
        self,
        *,
        unit_of_work_factory: FixedIncomeBookCostAuthorityUnitOfWorkFactory,
        policies: AmortizedCostPolicyRegistry,
        correction_replay_enabled: bool = False,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._policies = policies
        self._correction_replay_enabled = correction_replay_enabled

    async def execute(
        self,
        event: FixedIncomeBookCostAuthorityEvent,
        *,
        correlation_id: str | None = None,
        traceparent: str | None = None,
    ) -> ApplyFixedIncomeBookCostAuthorityEventResult:
        """Persist and atomically rebuild every profile boundary affected by the event."""

        mapped = map_fixed_income_book_cost_authority_event(event)
        effective_date = event.authority.header.valid_from
        async with self._unit_of_work_factory() as unit_of_work:
            writer = PersistLotAmortizedCostAuthorityUseCase(unit_of_work.authority)
            persistence = await writer.execute((mapped,))
            materializer = MaterializeLotAmortizedCostProfileUseCase(
                authority=unit_of_work.authority,
                profiles=unit_of_work.profiles,
            )
            replay_start = await self._replay_start(
                authority=unit_of_work.authority,
                mapped=mapped,
                persistence=persistence,
                default=effective_date,
            )
            affected_boundaries = sorted(
                {
                    replay_start,
                    effective_date,
                    *await unit_of_work.profiles.effective_boundaries_from(
                        mapped.scope,
                        effective_date=replay_start,
                    ),
                }
            )
            materialization_results: list[LotAmortizedCostMaterializationResult] = []
            for boundary in affected_boundaries:
                materialization_results.append(
                    await self._materialize_boundary(
                        authority=unit_of_work.authority,
                        materializer=materializer,
                        scope=mapped.scope,
                        effective_date=boundary,
                    )
                )
            materializations = tuple(materialization_results)
            primary_index = affected_boundaries.index(effective_date)
            materialization = materializations[primary_index]
            rematerializations = tuple(
                result for index, result in enumerate(materializations) if index != primary_index
            )
            correction_replay_intent = await self._stage_correction_replay(
                replay=unit_of_work.correction_replay,
                event=event,
                scope=mapped.scope,
                persistence=persistence,
                replay_start=replay_start,
                boundaries=tuple(affected_boundaries),
                materializations=materializations,
                correlation_id=correlation_id,
                traceparent=traceparent,
            )
            await unit_of_work.commit()
        return ApplyFixedIncomeBookCostAuthorityEventResult(
            scope=mapped.scope,
            persistence=persistence,
            materialization=materialization,
            rematerializations=rematerializations,
            correction_replay_intent=correction_replay_intent,
        )

    async def _stage_correction_replay(
        self,
        *,
        replay: FixedIncomeBookCostCorrectionReplayPort,
        event: FixedIncomeBookCostAuthorityEvent,
        scope: LotBookCostAuthorityScope,
        persistence: PersistLotAmortizedCostAuthorityResult,
        replay_start: date,
        boundaries: tuple[date, ...],
        materializations: tuple[LotAmortizedCostMaterializationResult, ...],
        correlation_id: str | None,
        traceparent: str | None,
    ) -> FixedIncomeBookCostCorrectionReplayIntent | None:
        """Stage one suffix replay only for a newly committed profile decision."""

        if not self._correction_replay_enabled:
            return None
        if persistence.appended_count == 0 or not any(
            result.outcome is LotAmortizedCostProfileAppendOutcome.APPENDED
            for result in materializations
        ):
            return None
        anchor = await replay.find_earliest_affected_disposal(
            scope,
            effective_date=replay_start,
        )
        if anchor is None:
            return None
        intent = FixedIncomeBookCostCorrectionReplayIntent(
            scope=scope,
            earliest_affected_date=replay_start,
            anchor=anchor,
            source_authority_event_content_hash=event.content_hash(),
            profile_decisions=tuple(
                FixedIncomeBookCostProfileDecisionEvidence(
                    effective_date=boundary,
                    profile_id=result.profile_id,
                    profile_version=result.profile_version,
                    authority_content_hash=result.authority_content_hash,
                    eligibility_reason=result.eligibility_reason,
                )
                for boundary, result in zip(boundaries, materializations, strict=True)
            ),
        )
        await replay.stage_replay_intent(
            intent,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
        return intent

    async def _replay_start(
        self,
        *,
        authority: LotAmortizedCostAuthorityPort,
        mapped: LotAmortizedCostAuthority,
        persistence: PersistLotAmortizedCostAuthorityResult,
        default: date,
    ) -> date:
        """Return the earliest boundary affected by an appended assignment correction."""

        if not isinstance(mapped, LotAmortizedCostPolicyAssignment):
            return default
        if persistence.appended_count == 0:
            return default
        bundle = await authority.load(mapped.scope)
        previous = _previous_assignment_version(bundle.assignments, current=mapped)
        if previous is None:
            return default
        return amortization_replay_start_for_assignment_correction(previous, mapped) or default

    async def _materialize_boundary(
        self,
        *,
        authority: LotAmortizedCostAuthorityPort,
        materializer: MaterializeLotAmortizedCostProfileUseCase,
        scope: LotBookCostAuthorityScope,
        effective_date: date,
    ) -> LotAmortizedCostMaterializationResult:
        policy, unresolved_reason = await self._resolve_policy(
            authority=authority,
            scope=scope,
            effective_date=effective_date,
        )
        if policy is not None:
            return await materializer.execute(
                scope=scope,
                effective_date=effective_date,
                policy=policy,
            )
        if unresolved_reason is None:
            raise RuntimeError("unresolved policy reason was not classified")
        return await materializer.execute_parked(
            scope=scope,
            effective_date=effective_date,
            reason=unresolved_reason,
        )

    async def _resolve_policy(
        self,
        *,
        authority: LotAmortizedCostAuthorityPort,
        scope: LotBookCostAuthorityScope,
        effective_date: date,
    ) -> tuple[AmortizedCostPolicy | None, AmortizedCostEligibilityReason | None]:
        bundle = await authority.load(scope)
        try:
            assignment = resolve_amortized_cost_assignment(
                list(bundle.assignments),
                scope=scope,
                effective_date=effective_date,
            ).assignment
        except MissingAmortizedCostAssignmentError:
            return None, AmortizedCostEligibilityReason.ASSIGNMENT_MISSING
        except OverlappingAmortizedCostAssignmentError:
            return None, AmortizedCostEligibilityReason.ASSIGNMENT_OVERLAPPING
        except AmortizedCostAuthorityError:
            return None, AmortizedCostEligibilityReason.ASSIGNMENT_CONFLICTING
        try:
            return (
                self._policies.resolve(
                    policy_id=assignment.policy_id,
                    policy_version=assignment.policy_version,
                ),
                None,
            )
        except UnsupportedAmortizedCostPolicyError:
            return None, AmortizedCostEligibilityReason.POLICY_UNSUPPORTED


def _previous_assignment_version(
    assignments: tuple[LotAmortizedCostPolicyAssignment, ...],
    *,
    current: LotAmortizedCostPolicyAssignment,
) -> LotAmortizedCostPolicyAssignment | None:
    previous_versions = (
        assignment
        for assignment in assignments
        if assignment.source_record_key == current.source_record_key
        and assignment.assignment_version < current.assignment_version
    )
    return max(
        previous_versions,
        key=lambda assignment: assignment.assignment_version,
        default=None,
    )
