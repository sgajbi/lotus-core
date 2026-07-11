"""SQLAlchemy source adapter for transaction-economics evidence products."""

from datetime import date, datetime, time, timedelta
from typing import cast

from portfolio_common.database_models import Cashflow, Portfolio, Transaction, TransactionCost
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager, joinedload

from ..domain.transaction_economics import (
    BookedTransactionEconomics,
    TransactionCashflowEvidence,
    TransactionCostComponentEvidence,
)


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _start_of_next_day(value: date) -> datetime:
    return datetime.combine(value + timedelta(days=1), time.min)


def _transaction_cost_curve_key_expressions():
    return (
        func.trim(Transaction.security_id),
        func.upper(func.trim(Transaction.transaction_type)),
        func.upper(func.trim(Transaction.currency)),
    )


def _transaction_cost_curve_after_key_predicate(after_key: tuple[str, str, str] | tuple[()]):
    if not after_key:
        return None
    security_id, transaction_type, currency = after_key
    security_expr, transaction_type_expr, currency_expr = _transaction_cost_curve_key_expressions()
    return or_(
        security_expr > security_id,
        and_(security_expr == security_id, transaction_type_expr > transaction_type),
        and_(
            security_expr == security_id,
            transaction_type_expr == transaction_type,
            currency_expr > currency,
        ),
    )


def _transaction_cost_curve_key_filter(curve_keys: list[tuple[str, str, str]]):
    security_expr, transaction_type_expr, currency_expr = _transaction_cost_curve_key_expressions()
    return or_(
        *[
            and_(
                security_expr == security_id,
                transaction_type_expr == transaction_type,
                currency_expr == currency,
            )
            for security_id, transaction_type, currency in curve_keys
        ]
    )


def _performance_component_economics_after_key_predicate(
    after_key: tuple[str, str, str] | tuple[()],
):
    if not after_key:
        return None
    security_id, transaction_date, transaction_id = after_key
    security_expr = func.trim(Transaction.security_id)
    transaction_date_expr = func.date(Transaction.transaction_date)
    return or_(
        security_expr > security_id,
        and_(security_expr == security_id, transaction_date_expr > transaction_date),
        and_(
            security_expr == security_id,
            transaction_date_expr == transaction_date,
            Transaction.transaction_id > transaction_id,
        ),
    )


def _cashflow_evidence(
    cashflow: Cashflow | None,
) -> TransactionCashflowEvidence | None:
    if cashflow is None:
        return None
    return TransactionCashflowEvidence(
        amount=cashflow.amount,
        currency=cashflow.currency,
        classification=cashflow.classification,
        timing=cashflow.timing,
        is_position_flow=cashflow.is_position_flow,
        is_portfolio_flow=cashflow.is_portfolio_flow,
        updated_at=cashflow.updated_at,
    )


def _cost_component_evidence(
    cost: TransactionCost,
) -> TransactionCostComponentEvidence:
    return TransactionCostComponentEvidence(
        fee_type=cost.fee_type,
        amount=cost.amount,
        currency=cost.currency,
        updated_at=cost.updated_at,
    )


def _booked_transaction_economics(
    transaction: Transaction,
) -> BookedTransactionEconomics:
    return BookedTransactionEconomics(
        transaction_id=transaction.transaction_id,
        portfolio_id=transaction.portfolio_id,
        security_id=transaction.security_id,
        transaction_type=transaction.transaction_type,
        currency=transaction.currency,
        trade_currency=transaction.trade_currency,
        transaction_date=transaction.transaction_date,
        gross_transaction_amount=transaction.gross_transaction_amount,
        allocated_cost_basis_local=transaction.allocated_cost_basis_local,
        allocated_cost_basis_base=transaction.allocated_cost_basis_base,
        trade_fee=transaction.trade_fee,
        withholding_tax_amount=transaction.withholding_tax_amount,
        other_interest_deductions_amount=transaction.other_interest_deductions_amount,
        net_interest_amount=transaction.net_interest_amount,
        realized_capital_pnl_local=transaction.realized_capital_pnl_local,
        realized_fx_pnl_local=transaction.realized_fx_pnl_local,
        realized_total_pnl_local=transaction.realized_total_pnl_local,
        realized_capital_pnl_base=transaction.realized_capital_pnl_base,
        realized_fx_pnl_base=transaction.realized_fx_pnl_base,
        realized_total_pnl_base=transaction.realized_total_pnl_base,
        transaction_fx_rate=transaction.transaction_fx_rate,
        fx_contract_id=transaction.fx_contract_id,
        cashflow=_cashflow_evidence(transaction.cashflow),
        costs=tuple(_cost_component_evidence(cost) for cost in transaction.costs),
        updated_at=transaction.updated_at,
    )


class SqlAlchemyTransactionEconomicsReader:
    """Read bounded transaction economics and map ORM rows into domain evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def get_portfolio_base_currency(self, portfolio_id: str) -> str | None:
        stmt = (
            select(Portfolio.base_currency).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        )
        return cast(str | None, (await self._session.execute(stmt)).scalar_one_or_none())

    async def list_transaction_cost_evidence(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None = None,
        transaction_types: list[str] | None = None,
        curve_keys: list[tuple[str, str, str]] | None = None,
    ) -> list[BookedTransactionEconomics]:
        stmt = (
            select(Transaction)
            .options(joinedload(Transaction.costs))
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_date >= _start_of_day(start_date),
                Transaction.transaction_date < _start_of_next_day(end_date),
                Transaction.transaction_date < _start_of_next_day(as_of_date),
                func.abs(Transaction.gross_transaction_amount) > 0,
                or_(
                    Transaction.trade_fee > 0,
                    exists(
                        select(1).where(
                            TransactionCost.transaction_id == Transaction.transaction_id,
                            TransactionCost.amount > 0,
                        )
                    ),
                ),
            )
        )
        if security_ids:
            normalized_security_ids = [
                normalized
                for security_id in security_ids
                if (normalized := normalize_lookup_identifier(security_id))
            ]
            if not normalized_security_ids:
                return []
            stmt = stmt.where(func.trim(Transaction.security_id).in_(normalized_security_ids))
        if transaction_types:
            stmt = stmt.where(Transaction.transaction_type.in_(transaction_types))
        if curve_keys is not None:
            if not curve_keys:
                return []
            stmt = stmt.where(_transaction_cost_curve_key_filter(curve_keys))
        stmt = stmt.order_by(
            Transaction.security_id.asc(),
            Transaction.transaction_type.asc(),
            Transaction.currency.asc(),
            Transaction.transaction_date.asc(),
            Transaction.transaction_id.asc(),
        )
        results = await self._session.execute(stmt)
        return [_booked_transaction_economics(row) for row in results.scalars().unique().all()]

    async def list_transaction_cost_curve_keys(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None = None,
        transaction_types: list[str] | None = None,
        min_observation_count: int,
        after_key: tuple[str, str, str] | tuple[()] = (),
        limit: int,
    ) -> list[tuple[str, str, str]]:
        security_expr, transaction_type_expr, currency_expr = (
            _transaction_cost_curve_key_expressions()
        )
        stmt = (
            select(
                security_expr.label("security_id"),
                transaction_type_expr.label("transaction_type"),
                currency_expr.label("currency"),
            )
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_date >= _start_of_day(start_date),
                Transaction.transaction_date < _start_of_next_day(end_date),
                Transaction.transaction_date < _start_of_next_day(as_of_date),
                func.abs(Transaction.gross_transaction_amount) > 0,
                or_(
                    Transaction.trade_fee > 0,
                    exists(
                        select(1).where(
                            TransactionCost.transaction_id == Transaction.transaction_id,
                            TransactionCost.amount > 0,
                        )
                    ),
                ),
            )
            .group_by(security_expr, transaction_type_expr, currency_expr)
            .having(func.count(Transaction.id) >= min_observation_count)
            .order_by(security_expr.asc(), transaction_type_expr.asc(), currency_expr.asc())
            .limit(limit)
        )

        if security_ids:
            normalized_security_ids = [
                normalized
                for security_id in security_ids
                if (normalized := normalize_lookup_identifier(security_id))
            ]
            if not normalized_security_ids:
                return []
            stmt = stmt.where(security_expr.in_(normalized_security_ids))
        if transaction_types:
            stmt = stmt.where(Transaction.transaction_type.in_(transaction_types))
        after_predicate = _transaction_cost_curve_after_key_predicate(after_key)
        if after_predicate is not None:
            stmt = stmt.where(after_predicate)

        result = await self._session.execute(stmt)
        return [
            (security_id, transaction_type, currency)
            for security_id, transaction_type, currency in result.all()
        ]

    async def list_transaction_cost_curve_available_security_ids(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None = None,
        transaction_types: list[str] | None = None,
        min_observation_count: int,
    ) -> set[str]:
        security_expr, transaction_type_expr, currency_expr = (
            _transaction_cost_curve_key_expressions()
        )
        eligible_groups = (
            select(security_expr.label("security_id"))
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_date >= _start_of_day(start_date),
                Transaction.transaction_date < _start_of_next_day(end_date),
                Transaction.transaction_date < _start_of_next_day(as_of_date),
                func.abs(Transaction.gross_transaction_amount) > 0,
                or_(
                    Transaction.trade_fee > 0,
                    exists(
                        select(1).where(
                            TransactionCost.transaction_id == Transaction.transaction_id,
                            TransactionCost.amount > 0,
                        )
                    ),
                ),
            )
            .group_by(security_expr, transaction_type_expr, currency_expr)
            .having(func.count(Transaction.id) >= min_observation_count)
        )
        if security_ids:
            normalized_security_ids = [
                normalized
                for security_id in security_ids
                if (normalized := normalize_lookup_identifier(security_id))
            ]
            if not normalized_security_ids:
                return set()
            eligible_groups = eligible_groups.where(security_expr.in_(normalized_security_ids))
        if transaction_types:
            eligible_groups = eligible_groups.where(
                Transaction.transaction_type.in_(transaction_types)
            )

        eligible_groups_subquery = eligible_groups.subquery()
        result = await self._session.execute(
            select(eligible_groups_subquery.c.security_id)
            .distinct()
            .order_by(eligible_groups_subquery.c.security_id.asc())
        )
        return set(result.scalars().all())

    async def list_performance_component_economics_evidence(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None = None,
        transaction_types: list[str] | None = None,
        after_key: tuple[str, str, str] | tuple[()] = (),
        limit: int | None = None,
    ) -> list[BookedTransactionEconomics]:
        ranked_cashflows = (
            select(
                Cashflow.id.label("id"),
                Cashflow.transaction_id.label("transaction_id"),
                func.row_number()
                .over(
                    partition_by=Cashflow.transaction_id,
                    order_by=(Cashflow.epoch.desc(), Cashflow.id.desc()),
                )
                .label("rn"),
            )
            .where(Cashflow.portfolio_id == portfolio_id)
            .subquery()
        )
        latest_cashflow = aliased(Cashflow)
        stmt = (
            select(Transaction)
            .outerjoin(
                ranked_cashflows,
                and_(
                    ranked_cashflows.c.transaction_id == Transaction.transaction_id,
                    ranked_cashflows.c.rn == 1,
                ),
            )
            .outerjoin(latest_cashflow, latest_cashflow.id == ranked_cashflows.c.id)
            .options(
                joinedload(Transaction.costs),
                contains_eager(Transaction.cashflow, alias=latest_cashflow),
            )
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_date >= _start_of_day(start_date),
                Transaction.transaction_date < _start_of_next_day(end_date),
                Transaction.transaction_date < _start_of_next_day(as_of_date),
            )
            .order_by(
                func.trim(Transaction.security_id).asc(),
                func.date(Transaction.transaction_date).asc(),
                Transaction.transaction_id.asc(),
            )
        )
        if security_ids:
            normalized_security_ids = [
                normalized
                for security_id in security_ids
                if (normalized := normalize_lookup_identifier(security_id))
            ]
            if not normalized_security_ids:
                return []
            stmt = stmt.where(func.trim(Transaction.security_id).in_(normalized_security_ids))
        if transaction_types:
            stmt = stmt.where(Transaction.transaction_type.in_(transaction_types))
        after_predicate = _performance_component_economics_after_key_predicate(after_key)
        if after_predicate is not None:
            stmt = stmt.where(after_predicate)
        if limit is not None:
            stmt = stmt.limit(limit)

        results = await self._session.execute(stmt)
        return [
            _booked_transaction_economics(transaction)
            for transaction in results.scalars().unique().all()
        ]
