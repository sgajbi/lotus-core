"""Port for bounded lot-to-position quantity reconciliation."""

from typing import Protocol

from ...domain.cost_basis.lot_position_reconciliation import (
    LotPositionParityAssessment,
    LotPositionParityKey,
)


class LotPositionParityPort(Protocol):
    async def assess_page(
        self,
        *,
        portfolio_id: str | None,
        after: LotPositionParityKey | None,
        limit: int,
    ) -> tuple[LotPositionParityAssessment, ...]: ...
