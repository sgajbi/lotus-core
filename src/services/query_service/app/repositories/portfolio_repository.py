# services/query-service/app/repositories/portfolio_repository.py
import logging
from datetime import date
from typing import List, Optional

from portfolio_common.database_models import Portfolio
from portfolio_common.logging_utils import operation_log_extra
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PortfolioRepository:
    """
    Handles read-only database queries for portfolio data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolios(
        self,
        portfolio_id: Optional[str] = None,
        portfolio_ids: Optional[list[str]] = None,
        client_id: Optional[str] = None,
        booking_center_code: Optional[str] = None,
    ) -> List[Portfolio]:
        """
        Retrieves a list of portfolios with optional filters.
        """
        stmt = select(Portfolio)

        if portfolio_id:
            stmt = stmt.filter_by(portfolio_id=portfolio_id)

        if portfolio_ids:
            stmt = stmt.where(Portfolio.portfolio_id.in_(portfolio_ids))

        if client_id:
            stmt = stmt.filter_by(client_id=client_id)

        if booking_center_code:
            stmt = stmt.filter_by(booking_center_code=booking_center_code)

        results = await self.db.execute(stmt.order_by(Portfolio.portfolio_id.asc()))
        portfolios = results.scalars().all()
        logger.info(
            "Portfolio repository query completed.",
            extra=operation_log_extra(
                event_name="query.portfolio_repository.query_completed",
                operation="query.portfolio_repository.get_portfolios",
                status="succeeded",
                reason_code="query_completed",
                result_count=len(portfolios),
                has_portfolio_id_filter=portfolio_id is not None,
                has_portfolio_ids_filter=bool(portfolio_ids),
                has_client_filter=client_id is not None,
                has_booking_center_filter=booking_center_code is not None,
            ),
        )
        return portfolios

    async def search_portfolio_lookup_ids(
        self,
        *,
        client_id: str | None = None,
        booking_center_code: str | None = None,
        q: str | None = None,
        limit: int,
    ) -> list[str]:
        """Return bounded portfolio IDs for selector workflows."""
        stmt = select(Portfolio.portfolio_id)

        if client_id:
            stmt = stmt.where(Portfolio.client_id == client_id)

        if booking_center_code:
            stmt = stmt.where(Portfolio.booking_center_code == booking_center_code)

        if q and (q_norm := q.strip().upper()):
            stmt = stmt.where(func.upper(Portfolio.portfolio_id).like(f"%{q_norm}%"))

        result = await self.db.execute(stmt.order_by(Portfolio.portfolio_id.asc()).limit(limit))
        return list(result.scalars().all())

    async def list_currency_lookup_codes(
        self,
        *,
        q: str | None = None,
        limit: int,
    ) -> list[str]:
        """Return bounded distinct portfolio base currencies for selector workflows."""
        currency_code = func.upper(func.trim(Portfolio.base_currency))
        stmt = (
            select(currency_code)
            .distinct()
            .where(Portfolio.base_currency.is_not(None))
            .where(func.trim(Portfolio.base_currency) != "")
        )

        if q and (q_norm := q.strip().upper()):
            stmt = stmt.where(currency_code.like(f"%{q_norm}%"))

        result = await self.db.execute(stmt.order_by(currency_code.asc()).limit(limit))
        return list(result.scalars().all())

    async def get_by_id(self, portfolio_id: str) -> Optional[Portfolio]:
        """Retrieves a single portfolio by its unique portfolio_id."""
        stmt = select(Portfolio).filter_by(portfolio_id=portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_portfolio_manager_book_members(
        self,
        *,
        portfolio_manager_id: str,
        as_of_date: date,
        booking_center_code: str | None = None,
        portfolio_types: list[str] | None = None,
        include_inactive: bool = False,
    ) -> list[Portfolio]:
        """Return deterministic portfolio master memberships for a PM/advisor book."""
        stmt = select(Portfolio).where(Portfolio.advisor_id == portfolio_manager_id)

        if booking_center_code:
            stmt = stmt.where(Portfolio.booking_center_code == booking_center_code)

        if portfolio_types:
            stmt = stmt.where(Portfolio.portfolio_type.in_(portfolio_types))

        if not include_inactive:
            stmt = stmt.where(Portfolio.open_date <= as_of_date)
            stmt = stmt.where(
                or_(Portfolio.close_date.is_(None), Portfolio.close_date >= as_of_date)
            )
            stmt = stmt.where(Portfolio.status == "ACTIVE")

        result = await self.db.execute(stmt.order_by(Portfolio.portfolio_id.asc()))
        return list(result.scalars().all())
