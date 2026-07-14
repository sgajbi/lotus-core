"""Framework-neutral persistence port for average-cost pool state."""

from typing import Protocol

from ...domain.cost_basis import (
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    AverageCostPoolTransition,
)
from .state_records import AverageCostPoolCheckpointRecord, AverageCostPoolPersistedSummary


class CostBasisAverageCostPoolPort(Protocol):
    """Persist the AVCO aggregate and its source-lot state atomically."""

    async def get_average_cost_pool_checkpoint_record(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> AverageCostPoolCheckpointRecord | None: ...

    async def upsert_average_cost_pool_checkpoint(
        self,
        checkpoint: AverageCostPoolCheckpoint,
    ) -> None: ...

    async def apply_average_cost_pool_transition(
        self,
        transition: AverageCostPoolTransition,
    ) -> None: ...

    async def apply_average_cost_pool_rebuild(
        self,
        plan: AverageCostPoolRebuildPlan,
    ) -> None: ...

    async def get_average_cost_pool_persisted_summary(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> AverageCostPoolPersistedSummary: ...
