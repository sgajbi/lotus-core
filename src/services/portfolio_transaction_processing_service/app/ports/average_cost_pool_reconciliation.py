from __future__ import annotations

from typing import Protocol

from ..domain.average_cost_pool_reconciliation import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationAssessment,
)


class AverageCostPoolReconciliationPort(Protocol):
    async def list_candidates(
        self,
        *,
        portfolio_id: str | None,
        after: AverageCostPoolKey | None,
        limit: int,
    ) -> tuple[AverageCostPoolKey, ...]: ...

    async def reconcile(
        self,
        *,
        key: AverageCostPoolKey,
        apply: bool,
    ) -> AverageCostPoolReconciliationAssessment: ...
