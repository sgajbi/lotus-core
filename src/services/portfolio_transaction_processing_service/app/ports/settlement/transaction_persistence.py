"""Persistence port for linked settlement transactions."""

from typing import Protocol

from ...domain.transaction import BookedTransaction


class SettlementTransactionPersistencePort(Protocol):
    """Persist one canonical booked settlement transaction."""

    async def upsert_booked_transaction(
        self,
        transaction: BookedTransaction,
        *,
        fields_to_clear: frozenset[str] = frozenset(),
    ) -> BookedTransaction: ...

    async def upsert_generated_booked_transaction(
        self,
        transaction: BookedTransaction,
        *,
        fields_to_clear: frozenset[str] = frozenset(),
    ) -> BookedTransaction: ...
