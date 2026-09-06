"""Source-owned tenant authority required before transaction processing."""

from __future__ import annotations

from typing import Protocol


class TransactionTenantAuthorityUnavailable(RuntimeError):
    """Raised when portfolio ownership is not yet durably available."""


class TransactionTenantAuthorityMismatch(ValueError):
    """Raised when asserted tenant scope conflicts with portfolio ownership."""


class TransactionTenantAuthorityPort(Protocol):
    async def resolve(
        self,
        *,
        portfolio_id: str,
        asserted_tenant_id: str | None,
    ) -> str: ...
