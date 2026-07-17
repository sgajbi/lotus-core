"""Persistence port for canonical cost-basis transaction state."""

from typing import Protocol

from ...domain.cost_basis import CostBasisTransaction
from ...domain.transaction import BookedTransaction


class CostBasisTransactionStatePort(Protocol):
    """Persist calculated transaction economics and load canonical history."""

    async def get_transaction_history(
        self,
        portfolio_id: str,
        security_id: str,
        exclude_id: str | None = None,
    ) -> list[BookedTransaction]: ...

    async def apply_transaction_costs_and_replace_breakdown(
        self,
        transaction: CostBasisTransaction,
    ) -> BookedTransaction | None: ...

    async def get_booked_transaction(
        self,
        transaction_id: str,
        *,
        portfolio_id: str | None = None,
    ) -> BookedTransaction | None: ...

    async def upsert_booked_transaction(self, transaction: BookedTransaction) -> None: ...
