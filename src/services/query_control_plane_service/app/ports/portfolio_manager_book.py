"""Source-read boundary for portfolio-manager book membership."""

from datetime import date
from typing import Protocol

from portfolio_common.domain.tenant import TenantId

from ..domain.portfolio_manager_book import PortfolioManagerBookRecord


class PortfolioManagerBookReader(Protocol):
    """Read effective portfolio-master membership without exposing ORM models."""

    async def list_members(
        self,
        *,
        tenant_id: TenantId,
        portfolio_manager_id: str,
        as_of_date: date,
        booking_center_code: str | None,
        portfolio_types: tuple[str, ...],
        include_inactive: bool,
    ) -> list[PortfolioManagerBookRecord]: ...
