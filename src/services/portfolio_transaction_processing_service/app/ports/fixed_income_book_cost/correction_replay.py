"""Application port for correction-triggered fixed-income disposal replay."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from ...domain.fixed_income_book_cost import (
    AffectedLotDisposalReplayAnchor,
    FixedIncomeBookCostCorrectionReplayIntent,
    LotBookCostAuthorityScope,
)


class FixedIncomeBookCostCorrectionReplayPort(Protocol):
    """Find and durably stage one affected source-lot replay suffix."""

    async def find_earliest_affected_disposal(
        self,
        scope: LotBookCostAuthorityScope,
        *,
        effective_date: date,
    ) -> AffectedLotDisposalReplayAnchor | None:
        """Return the earliest current disposal using the source lot after the boundary."""

        ...

    async def stage_replay_intent(
        self,
        intent: FixedIncomeBookCostCorrectionReplayIntent,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None:
        """Stage one intent in the caller-owned transaction."""

        ...
