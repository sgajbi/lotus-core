"""Define the application port for staging calculated transaction effects."""

from collections.abc import Sequence
from typing import Protocol

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import FxContractInstrument


class CostProcessingEffectStagingPort(Protocol):
    """Stage processed transactions and derived instruments in the active unit of work."""

    async def stage_processed_transactions(
        self,
        transactions: Sequence[BookedTransaction],
        *,
        correlation_id: str,
    ) -> None: ...

    async def stage_instrument_updates(
        self,
        instruments: Sequence[FxContractInstrument],
        *,
        correlation_id: str,
    ) -> None: ...
