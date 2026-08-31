from __future__ import annotations

from collections.abc import Sequence

from portfolio_common.database_models import Portfolio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..ports.portfolio_tenant_ownership import PortfolioTenantOwnershipReadError


class SqlAlchemyPortfolioTenantOwnershipReader:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def read_owned_portfolio_ids(
        self,
        *,
        tenant_id: str,
        portfolio_ids: Sequence[str],
    ) -> frozenset[str]:
        if not portfolio_ids:
            return frozenset()
        try:
            rows = await self._db.scalars(
                select(Portfolio.portfolio_id).where(
                    Portfolio.portfolio_id.in_(tuple(portfolio_ids)),
                    Portfolio.tenant_id == tenant_id,
                )
            )
        except SQLAlchemyError as exc:
            raise PortfolioTenantOwnershipReadError(
                "Portfolio tenant ownership lookup is unavailable."
            ) from exc
        return frozenset(str(portfolio_id) for portfolio_id in rows.all())
