from typing import cast

from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    Cashflow,
    Portfolio,
    PositionLotState,
    Transaction,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .identifier_normalization import normalize_security_id


class BuyStateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_position_lots(
        self, portfolio_id: str, security_id: str
    ) -> list[PositionLotState]:
        security_id = normalize_security_id(security_id)
        if not security_id:
            return []

        stmt = (
            select(PositionLotState)
            .where(
                PositionLotState.portfolio_id == portfolio_id,
                func.trim(PositionLotState.security_id) == security_id,
            )
            .order_by(PositionLotState.acquisition_date.asc(), PositionLotState.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_accrued_offsets(
        self, portfolio_id: str, security_id: str
    ) -> list[AccruedIncomeOffsetState]:
        security_id = normalize_security_id(security_id)
        if not security_id:
            return []

        stmt = (
            select(AccruedIncomeOffsetState)
            .where(
                AccruedIncomeOffsetState.portfolio_id == portfolio_id,
                func.trim(AccruedIncomeOffsetState.security_id) == security_id,
            )
            .order_by(AccruedIncomeOffsetState.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_buy_cash_linkage(
        self, portfolio_id: str, transaction_id: str
    ) -> tuple[Transaction, Cashflow | None] | None:
        stmt = (
            select(Transaction, Cashflow)
            .outerjoin(Cashflow, Cashflow.transaction_id == Transaction.transaction_id)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_id == transaction_id,
            )
            .limit(1)
        )
        return cast(
            tuple[Transaction, Cashflow | None] | None,
            (await self.db.execute(stmt)).first(),
        )
