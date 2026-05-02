from datetime import date
from typing import Optional

from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    Cashflow,
    Portfolio,
    PositionLotState,
    Transaction,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class BuyStateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_position_lots(
        self, portfolio_id: str, security_id: str
    ) -> list[PositionLotState]:
        stmt = (
            select(PositionLotState)
            .where(
                PositionLotState.portfolio_id == portfolio_id,
                PositionLotState.security_id == security_id,
            )
            .order_by(PositionLotState.acquisition_date.asc(), PositionLotState.id.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def list_portfolio_tax_lots(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        security_ids: list[str] | None,
        include_closed_lots: bool,
        lot_status_filter: str | None,
        after_sort_key: tuple[date, str] | None,
        limit: int,
    ) -> list[tuple[PositionLotState, str | None]]:
        filters = [
            PositionLotState.portfolio_id == portfolio_id,
            PositionLotState.acquisition_date <= as_of_date,
        ]
        if security_ids:
            filters.append(PositionLotState.security_id.in_(security_ids))
        status_filter = (lot_status_filter or "").upper()
        if status_filter == "OPEN" or (not include_closed_lots and status_filter != "CLOSED"):
            filters.append(PositionLotState.open_quantity > 0)
        elif status_filter == "CLOSED":
            filters.append(PositionLotState.open_quantity <= 0)
        if after_sort_key is not None:
            acquisition_date, lot_id = after_sort_key
            filters.append(
                or_(
                    PositionLotState.acquisition_date > acquisition_date,
                    and_(
                        PositionLotState.acquisition_date == acquisition_date,
                        PositionLotState.lot_id > lot_id,
                    ),
                )
            )
        stmt = (
            select(PositionLotState, Transaction.trade_currency)
            .outerjoin(
                Transaction,
                Transaction.transaction_id == PositionLotState.source_transaction_id,
            )
            .where(*filters)
            .order_by(
                PositionLotState.acquisition_date.asc(),
                PositionLotState.lot_id.asc(),
            )
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).all())

    async def get_accrued_offsets(
        self, portfolio_id: str, security_id: str
    ) -> list[AccruedIncomeOffsetState]:
        stmt = (
            select(AccruedIncomeOffsetState)
            .where(
                AccruedIncomeOffsetState.portfolio_id == portfolio_id,
                AccruedIncomeOffsetState.security_id == security_id,
            )
            .order_by(AccruedIncomeOffsetState.id.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_buy_cash_linkage(
        self, portfolio_id: str, transaction_id: str
    ) -> Optional[tuple[Transaction, Optional[Cashflow]]]:
        stmt = (
            select(Transaction, Cashflow)
            .outerjoin(Cashflow, Cashflow.transaction_id == Transaction.transaction_id)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_id == transaction_id,
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).first()
