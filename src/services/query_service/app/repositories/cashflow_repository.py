# src/services/query_service/app/repositories/cashflow_repository.py
import logging
from dataclasses import dataclass
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

from .date_filters import start_of_day, start_of_next_day
from .identifier_normalization import normalize_security_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CashflowSeriesEvidence:
    rows: list[tuple[date, Decimal]]
    latest_evidence_timestamp: datetime | None


class CashflowRepository:
    """
    Handles read-only database queries for cashflow data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _latest_cashflows_subquery(*, portfolio_id: str | None = None):
        ranked_cashflows = select(
            Cashflow.id.label("id"),
            func.row_number()
            .over(
                partition_by=Cashflow.transaction_id,
                order_by=(Cashflow.epoch.desc(), Cashflow.id.desc()),
            )
            .label("rn"),
        )
        if portfolio_id is not None:
            ranked_cashflows = ranked_cashflows.where(Cashflow.portfolio_id == portfolio_id)
        ranked_cashflows = ranked_cashflows.subquery()
        return (
            select(Cashflow)
            .join(ranked_cashflows, ranked_cashflows.c.id == Cashflow.id)
            .where(ranked_cashflows.c.rn == 1)
            .subquery()
        )

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_portfolio_currency(self, portfolio_id: str) -> str | None:
        stmt = (
            select(Portfolio.base_currency).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

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
        evidence = await self.get_portfolio_cashflow_series_with_evidence(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        return evidence.rows

    async def get_portfolio_cashflow_series_with_evidence(
        self, portfolio_id: str, start_date: date, end_date: date
    ) -> CashflowSeriesEvidence:
        """Return booked daily cashflows and latest evidence timestamp in one read."""
        latest_cashflows = self._latest_cashflows_subquery(portfolio_id=portfolio_id)
        stmt = (
            select(
                latest_cashflows.c.cashflow_date,
                func.sum(latest_cashflows.c.amount).label("net_amount"),
                func.max(latest_cashflows.c.updated_at).label("latest_evidence_timestamp"),
            )
            .where(
                latest_cashflows.c.portfolio_id == portfolio_id,
                latest_cashflows.c.cashflow_date.between(start_date, end_date),
                latest_cashflows.c.is_portfolio_flow,
            )
            .group_by(latest_cashflows.c.cashflow_date)
            .order_by(latest_cashflows.c.cashflow_date.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        return CashflowSeriesEvidence(
            rows=[(flow_date, net_amount) for flow_date, net_amount, _timestamp in rows],
            latest_evidence_timestamp=max(
                (timestamp for _flow_date, _net_amount, timestamp in rows if timestamp),
                default=None,
            ),
        )

    @async_timed(repository="CashflowRepository", method="get_projected_settlement_cashflow_series")
    async def get_projected_settlement_cashflow_series(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> List[Tuple[date, Decimal]]:
        """Projects future external settlement movements not yet present in booked cashflows."""
        evidence = await self.get_projected_settlement_cashflow_series_with_evidence(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        return evidence.rows

    async def get_projected_settlement_cashflow_series_with_evidence(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> CashflowSeriesEvidence:
        """Return projected settlement cashflows and latest evidence timestamp in one read."""
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
                func.max(Transaction.updated_at).label("latest_evidence_timestamp"),
            )
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_type.in_(("DEPOSIT", "WITHDRAWAL")),
                Transaction.settlement_date.is_not(None),
                Transaction.settlement_date >= start_of_day(start_date),
                Transaction.settlement_date < start_of_next_day(end_date),
                Transaction.transaction_date < start_of_day(start_date),
            )
            .group_by(settlement_date)
            .order_by(settlement_date.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        return CashflowSeriesEvidence(
            rows=[(flow_date, net_amount) for flow_date, net_amount, _timestamp in rows],
            latest_evidence_timestamp=max(
                (timestamp for _flow_date, _net_amount, timestamp in rows if timestamp),
                default=None,
            ),
        )

    @async_timed(repository="CashflowRepository", method="get_portfolio_cash_movement_summary")
    async def get_portfolio_cash_movement_summary(
        self, portfolio_id: str, start_date: date, end_date: date
    ) -> list[tuple[str, str, str, bool, bool, int, Decimal, datetime | None]]:
        """Aggregate latest cashflow rows by source-owned cash movement classification."""
        latest_cashflows = self._latest_cashflows_subquery(portfolio_id=portfolio_id)
        stmt = (
            select(
                latest_cashflows.c.classification,
                latest_cashflows.c.timing,
                latest_cashflows.c.currency,
                latest_cashflows.c.is_position_flow,
                latest_cashflows.c.is_portfolio_flow,
                func.count().label("cashflow_count"),
                func.sum(latest_cashflows.c.amount).label("total_amount"),
                func.max(latest_cashflows.c.updated_at).label("latest_evidence_timestamp"),
            )
            .where(
                latest_cashflows.c.portfolio_id == portfolio_id,
                latest_cashflows.c.cashflow_date.between(start_date, end_date),
            )
            .group_by(
                latest_cashflows.c.classification,
                latest_cashflows.c.timing,
                latest_cashflows.c.currency,
                latest_cashflows.c.is_position_flow,
                latest_cashflows.c.is_portfolio_flow,
            )
            .order_by(
                latest_cashflows.c.classification.asc(),
                latest_cashflows.c.timing.asc(),
                latest_cashflows.c.currency.asc(),
                latest_cashflows.c.is_portfolio_flow.desc(),
                latest_cashflows.c.is_position_flow.desc(),
            )
        )
        return (await self.db.execute(stmt)).all()

    @async_timed(repository="CashflowRepository", method="get_external_flows")
    async def get_external_flows(
        self, portfolio_id: str, start_date: date, end_date: date
    ) -> List[Tuple[date, Decimal]]:
        """
        Fetches only the external investor cashflows for a portfolio within a date range.
        These are used for MWR (IRR) calculations.
        """
        latest_cashflows = self._latest_cashflows_subquery(portfolio_id=portfolio_id)
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
        security_id = normalize_security_id(security_id)
        if not security_id:
            return []

        cashflow_security_id = func.trim(Cashflow.security_id)
        state_security_id = func.trim(PositionState.security_id)
        stmt = (
            select(Cashflow)
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == Cashflow.portfolio_id,
                    state_security_id == cashflow_security_id,
                    PositionState.epoch == Cashflow.epoch,
                ),
            )
            .where(
                Cashflow.portfolio_id == portfolio_id,
                cashflow_security_id == security_id,
                Cashflow.cashflow_date.between(start_date, end_date),
                Cashflow.classification == "INCOME",
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
