"""Persistence port for validated foreign-exchange transactions."""

from typing import Protocol

from ...domain.transaction import BookedTransaction


class ForeignExchangeTransactionPersistencePort(Protocol):
    """Persist one canonical foreign-exchange transaction component."""

    async def upsert_booked_transaction(self, transaction: BookedTransaction) -> None: ...
