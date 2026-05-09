# services/query-service/app/repositories/transaction_repository.py
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import BusinessDate, FxRate, Portfolio, Transaction
from portfolio_common.utils import async_timed
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .date_filters import start_of_day, start_of_next_day

logger = logging.getLogger(__name__)

# Whitelist of columns that clients are allowed to sort by.
ALLOWED_SORT_FIELDS = {
    "transaction_date",
    "settlement_date",
    "quantity",
    "price",
    "gross_transaction_amount",
}


class TransactionRepository:
    """
    Handles read-only database queries for transaction data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_latest_business_date(self) -> Optional[date]:
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_fx_rate(
        self,
        *,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Optional[float | Decimal]:
        if from_currency == to_currency:
            return Decimal("1")
        stmt = (
            select(FxRate.rate)
            .where(
                FxRate.from_currency == from_currency,
                FxRate.to_currency == to_currency,
                FxRate.rate_date <= as_of_date,
            )
            .order_by(FxRate.rate_date.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt,
        *,
        portfolio_id: str,
        instrument_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_type: Optional[str] = None,
        component_type: Optional[str] = None,
        linked_transaction_group_id: Optional[str] = None,
        fx_contract_id: Optional[str] = None,
        swap_event_id: Optional[str] = None,
        near_leg_group_id: Optional[str] = None,
        far_leg_group_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ):
        stmt = stmt.filter_by(portfolio_id=portfolio_id)
        if instrument_id:
            stmt = stmt.filter_by(instrument_id=instrument_id)
        if security_id:
            stmt = stmt.filter_by(security_id=security_id)
        if transaction_type:
            stmt = stmt.filter_by(transaction_type=transaction_type)
        if component_type:
            stmt = stmt.filter_by(component_type=component_type)
        if linked_transaction_group_id:
            stmt = stmt.filter_by(linked_transaction_group_id=linked_transaction_group_id)
        if fx_contract_id:
            stmt = stmt.filter_by(fx_contract_id=fx_contract_id)
        if swap_event_id:
            stmt = stmt.filter_by(swap_event_id=swap_event_id)
        if near_leg_group_id:
            stmt = stmt.filter_by(near_leg_group_id=near_leg_group_id)
        if far_leg_group_id:
            stmt = stmt.filter_by(far_leg_group_id=far_leg_group_id)
        if start_date:
            stmt = stmt.filter(Transaction.transaction_date >= start_of_day(start_date))
        if end_date:
            stmt = stmt.filter(Transaction.transaction_date < start_of_next_day(end_date))
        if as_of_date:
            stmt = stmt.filter(Transaction.transaction_date < start_of_next_day(as_of_date))
        return stmt

    def _get_base_query(
        self,
        portfolio_id: str,
        instrument_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_type: Optional[str] = None,
        component_type: Optional[str] = None,
        linked_transaction_group_id: Optional[str] = None,
        fx_contract_id: Optional[str] = None,
        swap_event_id: Optional[str] = None,
        near_leg_group_id: Optional[str] = None,
        far_leg_group_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ):
        """
        Constructs a base query with all the common filters.
        """
        stmt = select(Transaction).options(
            joinedload(Transaction.cashflow), joinedload(Transaction.costs)
        )
        return self._apply_filters(
            stmt,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            security_id=security_id,
            transaction_type=transaction_type,
            component_type=component_type,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )

    @async_timed(repository="TransactionRepository", method="get_transactions")
    async def get_transactions(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = "desc",
        instrument_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_type: Optional[str] = None,
        component_type: Optional[str] = None,
        linked_transaction_group_id: Optional[str] = None,
        fx_contract_id: Optional[str] = None,
        swap_event_id: Optional[str] = None,
        near_leg_group_id: Optional[str] = None,
        far_leg_group_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ) -> List[Transaction]:
        """
        Retrieves a paginated list of transactions with optional filters.
        """
        stmt = self._get_base_query(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            security_id=security_id,
            transaction_type=transaction_type,
            component_type=component_type,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )

        sort_field = "transaction_date"
        if sort_by and sort_by in ALLOWED_SORT_FIELDS:
            sort_field = sort_by

        normalized_sort_order = (sort_order or "desc").lower()
        sort_direction = asc if normalized_sort_order == "asc" else desc
        order_clause = sort_direction(getattr(Transaction, sort_field))

        stmt = stmt.order_by(order_clause)

        results = await self.db.execute(stmt.offset(skip).limit(limit))
        transactions = results.scalars().unique().all()
        logger.info(
            "Found %s transactions for portfolio '%s' with given filters.",
            len(transactions),
            portfolio_id,
        )
        return transactions

    @async_timed(repository="TransactionRepository", method="get_transactions_count")
    async def get_transactions_count(
        self,
        portfolio_id: str,
        instrument_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_type: Optional[str] = None,
        component_type: Optional[str] = None,
        linked_transaction_group_id: Optional[str] = None,
        fx_contract_id: Optional[str] = None,
        swap_event_id: Optional[str] = None,
        near_leg_group_id: Optional[str] = None,
        far_leg_group_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ) -> int:
        """
        Returns the total count of transactions for the given filters.
        """
        stmt = self._apply_filters(
            select(func.count(Transaction.id)),
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            security_id=security_id,
            transaction_type=transaction_type,
            component_type=component_type,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )

        count = (await self.db.execute(stmt)).scalar() or 0
        return count

    async def list_transaction_cost_evidence(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None = None,
        transaction_types: list[str] | None = None,
    ) -> List[Transaction]:
        stmt = (
            select(Transaction)
            .options(joinedload(Transaction.costs))
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_date >= start_of_day(start_date),
                Transaction.transaction_date < start_of_next_day(end_date),
                Transaction.transaction_date < start_of_next_day(as_of_date),
            )
        )
        if security_ids:
            stmt = stmt.where(Transaction.security_id.in_(security_ids))
        if transaction_types:
            stmt = stmt.where(Transaction.transaction_type.in_(transaction_types))
        stmt = stmt.order_by(
            Transaction.security_id.asc(),
            Transaction.transaction_type.asc(),
            Transaction.currency.asc(),
            Transaction.transaction_date.asc(),
            Transaction.transaction_id.asc(),
        )
        results = await self.db.execute(stmt)
        return list(results.scalars().unique().all())

    async def get_latest_evidence_timestamp(
        self,
        portfolio_id: str,
        instrument_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_type: Optional[str] = None,
        component_type: Optional[str] = None,
        linked_transaction_group_id: Optional[str] = None,
        fx_contract_id: Optional[str] = None,
        swap_event_id: Optional[str] = None,
        near_leg_group_id: Optional[str] = None,
        far_leg_group_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ) -> Optional[datetime]:
        """
        Returns the latest durable transaction evidence timestamp for the filtered ledger window.
        """
        stmt = self._apply_filters(
            select(func.max(Transaction.updated_at)),
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            security_id=security_id,
            transaction_type=transaction_type,
            component_type=component_type,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
