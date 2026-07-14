"""Define durable cashflow persistence required by the application layer."""

from typing import Protocol

from ...domain.cashflow import CalculatedCashflow, StoredCashflow


class CashflowPersistencePort(Protocol):
    """Create or restore one transaction/epoch cashflow ledger row."""

    async def create(self, cashflow: CalculatedCashflow) -> StoredCashflow: ...

    async def replace(self, cashflow: CalculatedCashflow) -> StoredCashflow: ...
