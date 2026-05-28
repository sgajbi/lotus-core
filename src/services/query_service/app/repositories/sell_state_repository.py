from typing import Optional

from portfolio_common.database_models import Cashflow, Portfolio, Transaction
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .identifier_normalization import normalize_security_id


class SellStateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

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
