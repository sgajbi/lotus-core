from typing import Optional

from portfolio_common.database_models import Cashflow, Transaction
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .identifier_normalization import normalize_security_id
from .portfolio_existence import portfolio_exists_for_tenant


class SellStateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str, *, tenant_id: TenantId) -> bool:
        """Whether the admitted tenant owns this portfolio.

        Delegates so the predicate lives in one place; see
        :mod:`portfolio_existence`.
        """
        return await portfolio_exists_for_tenant(self.db, portfolio_id, tenant_id=tenant_id)

    async def get_sell_disposals(self, portfolio_id: str, security_id: str) -> list[Transaction]:
        security_id = normalize_security_id(security_id)
        if not security_id:
            return []

        stmt = (
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio_id,
                func.trim(Transaction.security_id) == security_id,
                Transaction.transaction_type == "SELL",
            )
            .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_sell_cash_linkage(
        self, portfolio_id: str, transaction_id: str
    ) -> Optional[tuple[Transaction, Optional[Cashflow]]]:
        stmt = (
            select(Transaction, Cashflow)
            .outerjoin(Cashflow, Cashflow.transaction_id == Transaction.transaction_id)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_id == transaction_id,
                Transaction.transaction_type == "SELL",
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).first()
