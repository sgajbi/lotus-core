"""Framework-neutral port for cost-basis lot state."""

from decimal import Decimal
from typing import Protocol

from ...domain.cost_basis import CostBasisTransaction, OpenLotState
from .state_records import OpenLotCheckpointRecord


class CostBasisLotStatePort(Protocol):
    """Persist open lots and load bounded disposal checkpoints."""

    async def get_open_lot_checkpoint_records(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> list[OpenLotCheckpointRecord]: ...

    async def get_fifo_disposal_lot_checkpoint_records(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        required_quantity: Decimal,
    ) -> list[OpenLotCheckpointRecord]: ...

    async def upsert_buy_lot_state(self, transaction: CostBasisTransaction) -> None: ...

    async def update_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None: ...

    async def update_selected_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None: ...
