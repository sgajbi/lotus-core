"""Framework-neutral port for cost-basis serialization and replay state."""

from typing import Protocol

from ...domain.cost_basis import CostBasisProcessingCheckpoint


class CostBasisProcessingStatePort(Protocol):
    """Serialize one cost-basis stream and persist its replay frontier."""

    async def acquire_cost_basis_processing_lock(
        self,
        portfolio_id: str,
        security_id: str,
    ) -> None: ...

    async def get_cost_basis_processing_checkpoint(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> CostBasisProcessingCheckpoint | None: ...

    async def upsert_cost_basis_processing_checkpoint(
        self,
        checkpoint: CostBasisProcessingCheckpoint,
    ) -> None: ...
