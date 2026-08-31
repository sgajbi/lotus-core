from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class PortfolioTenantOwnershipReadError(Exception):
    """Authoritative portfolio ownership could not be read."""


class PortfolioTenantOwnershipReader(Protocol):
    async def read_owned_portfolio_ids(
        self,
        *,
        tenant_id: str,
        portfolio_ids: Sequence[str],
    ) -> frozenset[str]: ...
