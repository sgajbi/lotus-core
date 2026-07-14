"""Run bounded average-cost-pool reconciliation through one application port."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.cost_basis.average_cost_pool_reconciliation import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationAssessment,
    AverageCostPoolReconciliationStatus,
)
from ...ports.cost_basis.average_cost_pool_reconciliation import (
    AverageCostPoolReconciliationPort,
)


@dataclass(frozen=True, slots=True)
class ReconcileAverageCostPoolsCommand:
    """Request one ordered, bounded AVCO reconciliation page."""

    apply: bool = False
    limit: int = 100
    portfolio_id: str | None = None
    after: AverageCostPoolKey | None = None

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 1_000:
            raise ValueError("Average cost reconciliation limit must be between 1 and 1000")
        if self.portfolio_id is not None:
            normalized_portfolio_id = self.portfolio_id.strip()
            if not normalized_portfolio_id:
                raise ValueError("Average cost reconciliation portfolio ID must not be blank")
            object.__setattr__(self, "portfolio_id", normalized_portfolio_id)


@dataclass(frozen=True, slots=True)
class ReconcileAverageCostPoolsResult:
    """Summarize one AVCO reconciliation page and its continuation cursor."""

    apply: bool
    assessments: tuple[AverageCostPoolReconciliationAssessment, ...]
    next_cursor: AverageCostPoolKey | None

    @property
    def current_count(self) -> int:
        return self._count(AverageCostPoolReconciliationStatus.CURRENT)

    @property
    def drifted_count(self) -> int:
        return self._count(AverageCostPoolReconciliationStatus.DRIFTED)

    @property
    def reconciled_count(self) -> int:
        return self._count(AverageCostPoolReconciliationStatus.RECONCILED)

    @property
    def failed_count(self) -> int:
        return self._count(AverageCostPoolReconciliationStatus.FAILED)

    def _count(self, status: AverageCostPoolReconciliationStatus) -> int:
        return sum(assessment.status is status for assessment in self.assessments)


class ReconcileAverageCostPoolsUseCase:
    """Assess or repair ordered average-cost-pool candidates through the port."""

    def __init__(self, reconciliation: AverageCostPoolReconciliationPort) -> None:
        self._reconciliation = reconciliation

    async def execute(
        self,
        command: ReconcileAverageCostPoolsCommand,
    ) -> ReconcileAverageCostPoolsResult:
        keys = await self._reconciliation.list_candidates(
            portfolio_id=command.portfolio_id,
            after=command.after,
            limit=command.limit,
        )
        if tuple(sorted(keys)) != keys or len(set(keys)) != len(keys):
            raise ValueError("Average cost reconciliation candidates must be unique and ordered")

        assessments: list[AverageCostPoolReconciliationAssessment] = []
        for key in keys:
            assessments.append(await self._reconciliation.reconcile(key=key, apply=command.apply))
        return ReconcileAverageCostPoolsResult(
            apply=command.apply,
            assessments=tuple(assessments),
            next_cursor=keys[-1] if len(keys) == command.limit else None,
        )
