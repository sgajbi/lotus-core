"""Define the application port for governed cashflow rule resolution."""

from typing import Protocol

from ...domain.cashflow import CashflowRule


class CashflowRuleResolutionPort(Protocol):
    """Resolve the current governed rule for a transaction type."""

    async def resolve(self, transaction_type: str) -> CashflowRule | None: ...
