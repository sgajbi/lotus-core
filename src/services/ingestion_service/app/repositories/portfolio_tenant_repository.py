"""SQLAlchemy adapter for ingestion portfolio-ownership validation."""

from __future__ import annotations

from portfolio_common.database_models import Portfolio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ports.portfolio_tenant_reader import PortfolioTenantOwnership


class SqlAlchemyPortfolioTenantReader:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve_ownership(
        self,
        *,
        tenant_id: str,
        portfolio_ids: set[str],
    ) -> PortfolioTenantOwnership:
        if not portfolio_ids:
            return PortfolioTenantOwnership(frozenset(), frozenset())
        result = await self._db.execute(
            select(Portfolio.portfolio_id, Portfolio.tenant_id).where(
                Portfolio.portfolio_id.in_(portfolio_ids)
            )
        )
        rows = tuple(result.all())
        return PortfolioTenantOwnership(
            existing_ids=frozenset(row.portfolio_id for row in rows),
            owned_ids=frozenset(row.portfolio_id for row in rows if row.tenant_id == tenant_id),
        )
