# src/services/query_service/app/repositories/cashflow_repository.py
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    Cashflow,
    Portfolio,
    PositionState,
    Transaction,
)
from portfolio_common.utils import async_timed
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CashflowRepository:
    """
    Handles read-only database queries for cashflow data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _latest_cashflows_subquery():
        ranked_cashflows = select(
            Cashflow.id.label("id"),
            func.row_number()
            .over(
                partition_by=Cashflow.transaction_id,
                order_by=(Cashflow.epoch.desc(), Cashflow.id.desc()),
            )
            .label("rn"),
        ).subquery()
        return (
            select(Cashflow)
            .join(ranked_cashflows, ranked_cashflows.c.id == Cashflow.id)
            .where(ranked_cashflows.c.rn == 1)
            .subquery()
        )

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_latest_business_date(self) -> Optional[date]:
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    @async_timed(repository="CashflowRepository", method="get_portfolio_cashflow_series")
    async def get_portfolio_cashflow_series(
        self, portfolio_id: str, start_date: date, end_date: date
    ) -> List[Tuple[date, Decimal]]:
        """Returns daily aggregated portfolio cashflows for projection windows."""
        latest_cashflows = self._latest_cashflows_subquery()
        stmt = (
            select(
                latest_cashflows.c.cashflow_date,
                func.sum(latest_cashflows.c.amount).label("net_amount"),
            )
            .where(
                latest_cashflows.c.portfolio_id == portfolio_id,
                latest_cashflows.c.cashflow_date.between(start_date, end_date),
                latest_cashflows.c.is_portfolio_flow,
            )
            .group_by(latest_cashflows.c.cashflow_date)
            .order_by(latest_cashflows.c.cashflow_date.asc())
        )
        return (await self.db.execute(stmt)).all()

    @async_timed(repository="CashflowRepository", method="get_projected_settlement_cashflow_series")
    async def get_projected_settlement_cashflow_series(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> List[Tuple[date, Decimal]]:
        """Projects future external settlement movements not yet present in booked cashflows."""
        settlement_date = func.date(Transaction.settlement_date)
        signed_amount = case(
            (
                Transaction.transaction_type == "DEPOSIT",
                func.abs(Transaction.gross_transaction_amount),
            ),
            (
                Transaction.transaction_type == "WITHDRAWAL",
                -func.abs(Transaction.gross_transaction_amount),
            ),
            else_=None,
        )
        stmt = (
            select(
                settlement_date.label("cashflow_date"),
                func.sum(signed_amount).label("net_amount"),
            )
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_type.in_(("DEPOSIT", "WITHDRAWAL")),
                Transaction.settlement_date.is_not(None),
                settlement_date.between(start_date, end_date),
                func.date(Transaction.transaction_date) < start_date,
            )
            .group_by(settlement_date)
            .order_by(settlement_date.asc())
        )
        return (await self.db.execute(stmt)).all()

    @async_timed(
        repository="CashflowRepository",
        method="get_latest_cashflow_evidence_timestamp",
    )
    async def get_latest_cashflow_evidence_timestamp(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        include_projected: bool,
    ) -> datetime | None:
        """Return the latest source timestamp across booked and projected cashflow evidence."""

        latest_cashflows = self._latest_cashflows_subquery()
        booked_stmt = select(func.max(latest_cashflows.c.updated_at)).where(
            latest_cashflows.c.portfolio_id == portfolio_id,
            latest_cashflows.c.cashflow_date.between(start_date, end_date),
            latest_cashflows.c.is_portfolio_flow,
        )
        latest_booked = (await self.db.execute(booked_stmt)).scalar_one_or_none()

        latest_projected = None
        if include_projected:
            settlement_date = func.date(Transaction.settlement_date)
            projected_stmt = select(func.max(Transaction.updated_at)).where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_type.in_(("DEPOSIT", "WITHDRAWAL")),
                Transaction.settlement_date.is_not(None),
                settlement_date.between(start_date, end_date),
                func.date(Transaction.transaction_date) < start_date,
            )
            latest_projected = (await self.db.execute(projected_stmt)).scalar_one_or_none()

        timestamps = [value for value in (latest_booked, latest_projected) if value is not None]
        if not timestamps:
            return None
        return max(timestamps)

    @async_timed(repository="CashflowRepository", method="get_external_flows")
    async def get_external_flows(
        self, portfolio_id: str, start_date: date, end_date: date
    ) -> List[Tuple[date, Decimal]]:
        """
        Fetches only the external investor cashflows for a portfolio within a date range.
        These are used for MWR (IRR) calculations.
        """
        latest_cashflows = self._latest_cashflows_subquery()
        stmt = (
            select(latest_cashflows.c.cashflow_date, latest_cashflows.c.amount)
            .where(
                latest_cashflows.c.portfolio_id == portfolio_id,
                latest_cashflows.c.cashflow_date.between(start_date, end_date),
                latest_cashflows.c.is_portfolio_flow,
                latest_cashflows.c.classification.in_(["CASHFLOW_IN", "CASHFLOW_OUT"]),
            )
            .order_by(latest_cashflows.c.cashflow_date.asc())
        )
        result = await self.db.execute(stmt)
        return result.all()

    @async_timed(repository="CashflowRepository", method="get_income_cashflows_for_position")
    async def get_income_cashflows_for_position(
        self, portfolio_id: str, security_id: str, start_date: date, end_date: date
    ) -> List[Cashflow]:
        """
        Retrieves all income-classified cashflow records for a single position
        within a date range, ensuring data is from the correct epoch.
        """
        stmt = (
            select(Cashflow)
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == Cashflow.portfolio_id,
                    PositionState.security_id == Cashflow.security_id,
                    PositionState.epoch == Cashflow.epoch,
                ),
            )
            .where(
                Cashflow.portfolio_id == portfolio_id,
                Cashflow.security_id == security_id,
                Cashflow.cashflow_date.between(start_date, end_date),
                Cashflow.classification == "INCOME",
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
