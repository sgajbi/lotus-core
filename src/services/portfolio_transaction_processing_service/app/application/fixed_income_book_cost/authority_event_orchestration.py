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
    LotBookCostAuthorityScope,
    MissingAmortizedCostAssignmentError,
    OverlappingAmortizedCostAssignmentError,
    UnsupportedAmortizedCostPolicyError,
    resolve_amortized_cost_assignment,
)
from ...ports import (
    LotAmortizedCostAuthorityPort,
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


class FixedIncomeBookCostAuthorityUnitOfWork(Protocol):
    """Atomic persistence boundary required by the authority event handler."""

    @property
    def authority(self) -> LotAmortizedCostAuthorityPort: ...

    @property
    def profiles(self) -> LotAmortizedCostProfilePort: ...

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
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._policies = policies

    async def execute(
        self,
        event: FixedIncomeBookCostAuthorityEvent,
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
            affected_boundaries = sorted(
                {
                    effective_date,
                    *await unit_of_work.profiles.effective_boundaries_from(
                        mapped.scope,
                        effective_date=effective_date,
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
            await unit_of_work.commit()
        return ApplyFixedIncomeBookCostAuthorityEventResult(
            scope=mapped.scope,
            persistence=persistence,
            materialization=materialization,
            rematerializations=rematerializations,
        )

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
