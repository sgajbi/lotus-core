"""Define transactional event staging for calculated cashflows."""

from typing import Protocol

from ...domain import BookedTransaction
from ...domain.cashflow import StoredCashflow


class CashflowEventStagingPort(Protocol):
    """Stage one calculated-cashflow event in the active transaction."""

    async def stage_calculated_cashflow(
        self,
        cashflow: StoredCashflow,
        source_transaction: BookedTransaction,
        *,
        correlation_id: str | None,
    ) -> None: ...
