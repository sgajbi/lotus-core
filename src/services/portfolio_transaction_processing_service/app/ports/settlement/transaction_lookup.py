"""Lookup port for validating linked settlement transactions."""

from typing import Protocol

from ...domain.transaction import BookedTransaction


class SettlementTransactionLookupPort(Protocol):
    """Load a canonical booked transaction within its portfolio boundary."""

    async def get_booked_transaction(
        self,
        transaction_id: str,
        *,
        portfolio_id: str | None = None,
    ) -> BookedTransaction | None: ...
