"""Port for fail-closed portfolio ownership classification during ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PortfolioTenantOwnership:
    """Partition requested identifiers into existing and tenant-owned portfolios."""

    existing_ids: frozenset[str]
    owned_ids: frozenset[str]


class PortfolioTenantReader(Protocol):
    async def resolve_ownership(
        self,
        *,
        tenant_id: str,
        portfolio_ids: set[str],
    ) -> PortfolioTenantOwnership: ...
