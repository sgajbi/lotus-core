"""Apply one source-owned fixed-income book-cost authority event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from portfolio_common.event_contracts import FixedIncomeBookCostAuthorityEvent

from ...domain.fixed_income_book_cost import AmortizedCostPolicy, LotBookCostAuthorityScope
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
