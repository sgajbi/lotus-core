# services/query-service/app/repositories/transaction_repository.py
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any, List, Mapping, Optional, cast

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    Cashflow,
    FxRate,
    Instrument,
    Portfolio,
    Transaction,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.infrastructure.transaction_cost_snapshot import (
    TransactionCostSnapshot,
    transaction_cost_snapshot_lateral,
    transaction_cost_snapshots,
)
from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.utils import async_timed
from sqlalchemy import asc, desc, func, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager

from ..application.transaction_query import (
    TransactionLedgerFilters,
    TransactionLedgerInputEvidence,
    TransactionLedgerQuerySpec,
)
from .currency_query_expressions import currency_code_sql_expr
from .date_filters import start_of_day, start_of_next_day
from .identifier_normalization import normalize_security_id
from .transaction_ledger_input_evidence import transaction_ledger_input_evidence_statement

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TransactionCashflowSnapshot:
    """Latest cashflow epoch attached to one transaction-ledger row."""

    amount: Decimal
    currency: str
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    calculation_type: str


@dataclass(frozen=True, slots=True)
class TransactionLedgerRow:
    """Persistence-independent ledger row captured in one SQL statement snapshot."""

    _values: Mapping[str, Any]
    costs: tuple[TransactionCostSnapshot, ...]
    cashflow: TransactionCashflowSnapshot | None

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _transaction_cashflow_snapshot(
    cashflow: Cashflow | None,
) -> TransactionCashflowSnapshot | None:
    if cashflow is None:
        return None
    return TransactionCashflowSnapshot(
        amount=cashflow.amount,
        currency=cashflow.currency,
        classification=cashflow.classification,
        timing=cashflow.timing,
        is_position_flow=cashflow.is_position_flow,
        is_portfolio_flow=cashflow.is_portfolio_flow,
        calculation_type=cashflow.calculation_type,
    )


def _transaction_ledger_row(
    *,
    transaction: Transaction,
    costs: tuple[TransactionCostSnapshot, ...],
) -> TransactionLedgerRow:
    return TransactionLedgerRow(
        _values=MappingProxyType(
            {
                column.name: getattr(transaction, column.name)
                for column in Transaction.__table__.columns
            }
        ),
        costs=costs,
        cashflow=_transaction_cashflow_snapshot(transaction.cashflow),
    )


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
        transaction_id=filters.transaction_id,
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

    async def establish_transaction_ledger_read_snapshot(self) -> None:
        """Make every material ledger read in this request share one database snapshot."""

        if self.db.in_transaction():
            raise RuntimeError(
                "Transaction ledger snapshot must be established before the first database read."
            )
        await self.db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))

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
    ) -> Decimal | None:
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
            .order_by(FxRate.rate_date.desc(), FxRate.id.desc())
            .limit(1)
        )
        return cast(Decimal | None, (await self.db.execute(stmt)).scalar_one_or_none())

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
        for field_name, value in _ledger_identity_filters(filters).items():
            stmt = stmt.where(getattr(Transaction, field_name) == value)
        stmt = _apply_security_filter(stmt, filters.security_id)
        return _apply_transaction_date_filters(
            stmt,
            start_date=filters.start_date,
            end_date=filters.end_date,
            as_of_date=filters.as_of_date,
        )

    @async_timed(repository="TransactionRepository", method="get_transactions")
    async def get_transactions(
        self,
        *,
        query_spec: TransactionLedgerQuerySpec,
        skip: int,
        limit: int,
    ) -> list[TransactionLedgerRow]:
        """
        Retrieves a paginated list of transactions with optional filters.
        """
        filters = query_spec.filters
        sort_direction = asc if query_spec.sort.order == "asc" else desc
        order_clause = sort_direction(getattr(Transaction, query_spec.sort.field))
        tie_breaker_clause = sort_direction(Transaction.id)

        page = (
            self._apply_filters(
                select(Transaction.id.label("transaction_pk")),
                filters=filters,
            )
            .order_by(order_clause, tie_breaker_clause)
            .offset(skip)
            .limit(limit)
            .subquery("transaction_page")
        )
        cost_snapshot = transaction_cost_snapshot_lateral(Transaction.transaction_id)
        latest_cashflow_row = (
            select(Cashflow)
            .where(Cashflow.transaction_id == Transaction.transaction_id)
            .order_by(Cashflow.epoch.desc(), Cashflow.id.desc())
            .limit(1)
            .correlate(Transaction)
            .lateral("latest_cashflow")
        )
        latest_cashflow = aliased(Cashflow, latest_cashflow_row)
        stmt = (
            select(
                Transaction,
                cost_snapshot.c.cost_fee_types,
                cost_snapshot.c.cost_amounts,
                cost_snapshot.c.cost_currencies,
                cost_snapshot.c.cost_updated_ats,
            )
            .join(page, Transaction.id == page.c.transaction_pk)
            .outerjoin(latest_cashflow, true())
            .join(cost_snapshot, true())
            .options(contains_eager(Transaction.cashflow, alias=latest_cashflow))
            .order_by(order_clause, tie_breaker_clause)
        )

        results = await self.db.execute(stmt)
        transactions = [
            _transaction_ledger_row(
                transaction=transaction,
                costs=transaction_cost_snapshots(
                    fee_types=fee_types,
                    amounts=amounts,
                    currencies=currencies,
                    updated_ats=updated_ats,
                ),
            )
            for transaction, fee_types, amounts, currencies, updated_ats in results.all()
        ]
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
        return transactions

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

    async def get_transaction_ledger_input_evidence(
        self,
        *,
        filters: TransactionLedgerFilters,
        reporting_currency: str | None,
        as_of_date: date | None,
    ) -> TransactionLedgerInputEvidence:
        """Return page-independent, fixed-width evidence for ledger reconstruction."""

        matching_transactions = self._apply_filters(
            select(
                Transaction.id.label("transaction_pk"),
                Transaction.transaction_id,
                Transaction.currency,
                Transaction.trade_currency,
            ),
            filters=filters,
        ).cte("matching_ledger_transactions")
        statement = transaction_ledger_input_evidence_statement(
            matching_transactions=matching_transactions,
            reporting_currency=reporting_currency,
            as_of_date=as_of_date,
        )
        row = (await self.db.execute(statement)).one()
        evidence_timestamps = (
            row.transaction_latest_at,
            row.transaction_cost_latest_at,
            row.selected_cashflow_latest_at,
            row.selected_fx_rate_latest_at,
        )
        latest_evidence_timestamp = max(
            (timestamp for timestamp in evidence_timestamps if timestamp is not None),
            default=None,
        )
        return TransactionLedgerInputEvidence(
            transaction_count=int(row.transaction_count or 0),
            latest_evidence_timestamp=latest_evidence_timestamp,
            transaction_digest=row.transaction_digest,
            transaction_cost_digest=row.transaction_cost_digest,
            selected_cashflow_digest=row.selected_cashflow_digest,
            selected_fx_rate_digest=row.selected_fx_rate_digest,
        )

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
