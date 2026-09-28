"""Portfolio-authority lookups shared by operational support queries."""

from portfolio_common.database_models import Portfolio
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PortfolioAuthorityRepositoryMixin:
    """Keep portfolio authority lookups out of the broad operations adapter."""

    db: AsyncSession

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def portfolio_exists_for_tenant(
        self,
        portfolio_id: str,
        *,
        tenant_id: TenantId,
    ) -> bool:
        stmt = (
            select(Portfolio.portfolio_id)
            .where(
                Portfolio.tenant_id == tenant_id.value,
                Portfolio.portfolio_id == portfolio_id,
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None


__all__ = ["PortfolioAuthorityRepositoryMixin"]
