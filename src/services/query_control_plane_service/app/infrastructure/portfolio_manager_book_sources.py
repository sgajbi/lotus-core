"""SQLAlchemy source adapter for portfolio-manager book membership."""

from datetime import date
from typing import Any

from portfolio_common.database_models import Portfolio
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.portfolio_manager_book import PortfolioManagerBookRecord


class SqlAlchemyPortfolioManagerBookReader:
    """Select deterministic effective memberships from the portfolio master."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_members(
        self,
        *,
        portfolio_manager_id: str,
        as_of_date: date,
        booking_center_code: str | None,
        portfolio_types: tuple[str, ...],
        include_inactive: bool,
    ) -> list[PortfolioManagerBookRecord]:
        statement = select(Portfolio).where(Portfolio.advisor_id == portfolio_manager_id)
        if booking_center_code:
            statement = statement.where(Portfolio.booking_center_code == booking_center_code)
        if portfolio_types:
            statement = statement.where(Portfolio.portfolio_type.in_(portfolio_types))
        if not include_inactive:
            statement = statement.where(
                Portfolio.open_date <= as_of_date,
                or_(Portfolio.close_date.is_(None), Portfolio.close_date >= as_of_date),
                Portfolio.status == "ACTIVE",
            )
        result = await self._session.execute(statement.order_by(Portfolio.portfolio_id.asc()))
        return [_portfolio_manager_book_record(row) for row in result.scalars().all()]


def _portfolio_manager_book_record(row: Any) -> PortfolioManagerBookRecord:
    return PortfolioManagerBookRecord(
        portfolio_id=row.portfolio_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        portfolio_type=row.portfolio_type,
        status=row.status,
        open_date=row.open_date,
        close_date=row.close_date,
        base_currency=row.base_currency,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
