# services/query-service/app/repositories/transaction_repository.py
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, cast

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    FxRate,
    Instrument,
    Portfolio,
    Transaction,
)
from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.utils import async_timed
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..application.transaction_query import TransactionLedgerFilters, TransactionLedgerQuerySpec
from .currency_codes import currency_code_sql_expr, normalize_currency_code
from .date_filters import start_of_day, start_of_next_day
from .identifier_normalization import normalize_security_id

logger = logging.getLogger(__name__)


def _identity_filter_kwargs(*, portfolio_id: str, **filters) -> dict[str, str]:
    return {
        field_name: value
        for field_name, value in {"portfolio_id": portfolio_id, **filters}.items()
        if value
    }


def _apply_security_filter(stmt, security_id: Optional[str]):
    normalized_security_id = normalize_security_id(security_id)
    if not normalized_security_id:
        return stmt
    return stmt.where(func.trim(Transaction.security_id) == normalized_security_id)


def _apply_transaction_date_filters(
    stmt,
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    as_of_date: Optional[date],
):
    date_filters = (
        (start_date, lambda value: Transaction.transaction_date >= start_of_day(value)),
        (end_date, lambda value: Transaction.transaction_date < start_of_next_day(value)),
        (as_of_date, lambda value: Transaction.transaction_date < start_of_next_day(value)),
    )
    for boundary_date, predicate_factory in date_filters:
        if boundary_date:
            stmt = stmt.filter(predicate_factory(boundary_date))
    return stmt


def _ledger_identity_filters(filters: TransactionLedgerFilters) -> dict[str, str]:
    return _identity_filter_kwargs(
        portfolio_id=filters.portfolio_id,
        instrument_id=filters.instrument_id,
        transaction_type=filters.transaction_type,
        component_type=filters.component_type,
        linked_transaction_group_id=filters.linked_transaction_group_id,
        fx_contract_id=filters.fx_contract_id,
        swap_event_id=filters.swap_event_id,
        near_leg_group_id=filters.near_leg_group_id,
        far_leg_group_id=filters.far_leg_group_id,
    )


class TransactionRepository:
    """
    Handles read-only database queries for transaction data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _realized_tax_evidence_predicate():
        return (Transaction.withholding_tax_amount.is_not(None)) | (
            Transaction.other_interest_deductions_amount.is_not(None)
        )

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_portfolio_base_currency(self, portfolio_id: str) -> Optional[str]:
        stmt = (
            select(Portfolio.base_currency).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        )
        return cast(Optional[str], (await self.db.execute(stmt)).scalar_one_or_none())

    async def get_latest_business_date(
        self,
        calendar_code: str = DEFAULT_BUSINESS_CALENDAR_CODE,
    ) -> Optional[date]:
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == calendar_code
        )
        return cast(Optional[date], (await self.db.execute(stmt)).scalar_one_or_none())

    async def get_latest_fx_rate(
        self,
        *,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Optional[float | Decimal]:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        if normalized_from_currency == normalized_to_currency:
            return Decimal("1")
        from_currency_expr = currency_code_sql_expr(FxRate.from_currency)
        to_currency_expr = currency_code_sql_expr(FxRate.to_currency)
        stmt = (
            select(FxRate.rate)
            .where(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date <= as_of_date,
            )
            .order_by(FxRate.rate_date.desc())
            .limit(1)
        )
        return cast(
            Optional[float | Decimal],
            (await self.db.execute(stmt)).scalar_one_or_none(),
        )

    async def list_known_instrument_security_ids(self, security_ids: list[str]) -> set[str]:
        normalized_security_ids = list(
            dict.fromkeys(
                normalized
                for security_id in security_ids
                if (normalized := normalize_security_id(security_id))
            )
        )
        if not normalized_security_ids:
            return set()

        instrument_security_id = func.trim(Instrument.security_id)
        stmt = select(instrument_security_id).where(
            instrument_security_id.in_(normalized_security_ids)
        )
        result = await self.db.execute(stmt)
        return set(result.scalars().all())

    def _apply_filters(
        self,
        stmt,
        *,
        filters: TransactionLedgerFilters,
    ):
        stmt = stmt.filter_by(**_ledger_identity_filters(filters))
        stmt = _apply_security_filter(stmt, filters.security_id)
        return _apply_transaction_date_filters(
            stmt,
            start_date=filters.start_date,
            end_date=filters.end_date,
            as_of_date=filters.as_of_date,
        )

    def _get_base_query(
        self,
        filters: TransactionLedgerFilters,
    ):
        """
        Constructs a base query with all the common filters.
        """
        stmt = select(Transaction).options(
            joinedload(Transaction.cashflow), joinedload(Transaction.costs)
        )
        return self._apply_filters(
            stmt,
            filters=filters,
        )

    @async_timed(repository="TransactionRepository", method="get_transactions")
    async def get_transactions(
        self,
        *,
        query_spec: TransactionLedgerQuerySpec,
        skip: int,
        limit: int,
    ) -> List[Transaction]:
        """
        Retrieves a paginated list of transactions with optional filters.
        """
        filters = query_spec.filters
        stmt = self._get_base_query(filters=filters)

        sort_direction = asc if query_spec.sort.order == "asc" else desc
        order_clause = sort_direction(getattr(Transaction, query_spec.sort.field))
        tie_breaker_clause = sort_direction(Transaction.id)

        stmt = stmt.order_by(order_clause, tie_breaker_clause)

        results = await self.db.execute(stmt.offset(skip).limit(limit))
        transactions = results.scalars().unique().all()
        logger.info(
            "Transaction repository query completed.",
            extra=operation_log_extra(
                event_name="query.transaction_repository.query_completed",
                operation="query.transaction_repository.get_transactions",
                status="succeeded",
                reason_code="query_completed",
                result_count=len(transactions),
                has_instrument_filter=filters.instrument_id is not None,
                has_security_filter=filters.security_id is not None,
                has_transaction_type_filter=filters.transaction_type is not None,
                has_component_type_filter=filters.component_type is not None,
                has_start_date_filter=filters.start_date is not None,
                has_end_date_filter=filters.end_date is not None,
                has_as_of_date_filter=filters.as_of_date is not None,
            ),
        )
        return cast(List[Transaction], transactions)

    @async_timed(repository="TransactionRepository", method="get_transactions_count")
    async def get_transactions_count(
        self,
        *,
        filters: TransactionLedgerFilters,
    ) -> int:
        """
        Returns the total count of transactions for the given filters.
        """
        stmt = self._apply_filters(
            select(func.count(Transaction.id)),
            filters=filters,
        )

        count = (await self.db.execute(stmt)).scalar() or 0
        return count

    async def get_latest_evidence_timestamp(
        self,
        *,
        filters: TransactionLedgerFilters,
    ) -> Optional[datetime]:
        """
        Returns the latest durable transaction evidence timestamp for the filtered ledger window.
        """
        stmt = self._apply_filters(
            select(func.max(Transaction.updated_at)),
            filters=filters,
        )
        return cast(Optional[datetime], (await self.db.execute(stmt)).scalar_one_or_none())

    async def list_realized_tax_evidence_transactions(
        self,
        *,
        filters: TransactionLedgerFilters,
    ) -> List[Transaction]:
        stmt = self._apply_filters(
            select(Transaction).where(self._realized_tax_evidence_predicate()),
            filters=filters,
        ).order_by(
            Transaction.currency.asc(),
            Transaction.transaction_date.asc(),
            Transaction.transaction_id.asc(),
        )
        results = await self.db.execute(stmt)
        return list(results.scalars().all())
