"""Persistence port for validated foreign-exchange transactions."""

from datetime import datetime
from typing import Protocol

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx.persisted_return import FxPersistenceWitness


class ForeignExchangeTransactionPersistencePort(Protocol):
    """Persist one canonical foreign-exchange transaction component."""

    async def upsert_booked_transaction(
        self,
        transaction: BookedTransaction,
    ) -> BookedTransaction: ...
    async def load_fx_retention_witness(
        self, transaction: BookedTransaction
    ) -> FxPersistenceWitness | None: ...
    async def load_fx_creation_timestamp(self) -> datetime:
        """Read server chronology in the existing financial transaction, without committing."""
        ...
