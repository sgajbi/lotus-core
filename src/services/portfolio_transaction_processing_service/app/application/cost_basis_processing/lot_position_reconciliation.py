"""Run a bounded read-only lot-to-position quantity audit."""

from dataclasses import dataclass

from ...domain.cost_basis.lot_position_reconciliation import (
    LotPositionParityAssessment,
    LotPositionParityKey,
    LotPositionParityStatus,
)
from ...ports.cost_basis.lot_position_reconciliation import LotPositionParityPort


@dataclass(frozen=True, slots=True)
class AuditLotPositionParityCommand:
    limit: int = 100
    portfolio_id: str | None = None
    after: LotPositionParityKey | None = None

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 1_000:
            raise ValueError("Lot-position parity limit must be between 1 and 1000")
        if self.portfolio_id is not None:
            normalized = self.portfolio_id.strip()
            if not normalized:
                raise ValueError("Lot-position parity portfolio ID must not be blank")
            object.__setattr__(self, "portfolio_id", normalized)


@dataclass(frozen=True, slots=True)
class AuditLotPositionParityResult:
    assessments: tuple[LotPositionParityAssessment, ...]
    next_cursor: LotPositionParityKey | None

    @property
    def current_count(self) -> int:
        return sum(item.status is LotPositionParityStatus.CURRENT for item in self.assessments)

    @property
    def drifted_count(self) -> int:
        return sum(item.status is LotPositionParityStatus.DRIFTED for item in self.assessments)


class AuditLotPositionParityUseCase:
    def __init__(self, reconciliation: LotPositionParityPort) -> None:
        self._reconciliation = reconciliation

    async def execute(
        self,
        command: AuditLotPositionParityCommand,
    ) -> AuditLotPositionParityResult:
        assessments = await self._reconciliation.assess_page(
            portfolio_id=command.portfolio_id,
            after=command.after,
            limit=command.limit,
        )
        keys = tuple(item.key for item in assessments)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("Lot-position parity assessments must be unique and ordered")
        return AuditLotPositionParityResult(
            assessments=assessments,
            next_cursor=keys[-1] if len(keys) == command.limit else None,
        )
