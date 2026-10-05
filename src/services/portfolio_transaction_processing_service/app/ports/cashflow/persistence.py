"""Define durable cashflow persistence required by the application layer."""

from dataclasses import dataclass
from typing import Protocol

from ...domain.cashflow import CalculatedCashflow, StoredCashflow
from ...domain.transaction import BookedTransaction


@dataclass(frozen=True, slots=True)
class MaterializedNoCashflowReceipt:
    """A pre-existing completed semantic stage for a declared no-cashflow route."""

    tenant_id: str
    portfolio_id: str
    transaction_id: str
    epoch: int


class CashflowPersistencePort(Protocol):
    """Create or restore one transaction/epoch cashflow ledger row."""

    async def load_materialized(
        self,
        cashflow: CalculatedCashflow,
        *,
        tenant_id: str,
        semantic_event_id: str,
    ) -> StoredCashflow | None:
        """Retain a pre-existing scoped cashflow and its semantic receipt."""
        ...

    async def load_materialized_no_effect(
        self, transaction: BookedTransaction, *, semantic_event_id: str
    ) -> MaterializedNoCashflowReceipt | None:
        """Require an existing scoped semantic receipt and no transaction/epoch ledger."""
        ...

    async def create(self, cashflow: CalculatedCashflow) -> StoredCashflow: ...

    async def replace(self, cashflow: CalculatedCashflow) -> StoredCashflow: ...
