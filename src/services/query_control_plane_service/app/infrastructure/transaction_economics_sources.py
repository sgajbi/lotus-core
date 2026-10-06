"""SQLAlchemy source adapter for transaction-economics evidence products."""

from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

from portfolio_common.database_models import (
    Cashflow,
    Portfolio,
    Transaction,
    TransactionCost,
)
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction.fx_source_admission import FX_SOURCE_ADMISSION_TYPES
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.infrastructure.transaction_cost_snapshot import (
    TransactionCostSnapshot,
    transaction_cost_snapshot_lateral,
    transaction_cost_snapshots,
)
from portfolio_common.infrastructure.transaction_source_evidence import (
    SqlAlchemyTransactionSourceEvidence,
)
from sqlalchemy import and_, exists, func, or_, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager

from ..domain.transaction_economics import (
    BookedTransactionEconomics,
    FxPnlSourceEvidence,
    TransactionCashflowEvidence,
    TransactionCostComponentEvidence,
)


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _start_of_next_day(value: date) -> datetime:
    return datetime.combine(value + timedelta(days=1), time.min, tzinfo=UTC)


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
    cost: TransactionCost | TransactionCostSnapshot,
) -> TransactionCostComponentEvidence:
    return TransactionCostComponentEvidence(
        fee_type=cost.fee_type,
        amount=cost.amount,
        currency=cost.currency,
        updated_at=cost.updated_at,
    )


def _booked_transaction_economics(
    transaction: Transaction,
    *,
    costs: tuple[TransactionCostSnapshot, ...],
    fx_pnl_source_evidence: FxPnlSourceEvidence | None = None,
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
        costs=tuple(_cost_component_evidence(cost) for cost in costs),
        updated_at=transaction.updated_at,
        fx_realized_pnl_mode=transaction.fx_realized_pnl_mode,
        component_type=transaction.component_type,
        fx_pnl_source_evidence=fx_pnl_source_evidence,
    )


class SqlAlchemyTransactionEconomicsReader:
    """Read bounded transaction economics and map ORM rows into domain evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._performance_snapshot = False
        self._performance_window: list[BookedTransactionEconomics] | None = None
        self._performance_scope: tuple | None = None

    async def establish_performance_read_snapshot(self) -> None:
        if self._session.in_transaction():
            raise RuntimeError("Performance snapshot must precede every database read")
        await self._session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        )
        self._performance_snapshot = True

    async def capture_performance_source_cut(
        self,
        *,
        portfolio_id: str,
        tenant_id: TenantId,
        portfolio_base_currency: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None,
        transaction_types: list[str] | None,
    ) -> str:
        if not self._performance_snapshot or self._performance_window is not None:
            raise RuntimeError("Performance source cut requires an initial repeatable snapshot")
        rows = await self.list_performance_component_economics_evidence(
            portfolio_id=portfolio_id,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            security_ids=security_ids,
            transaction_types=transaction_types,
            after_key=(),
            limit=None,
        )
        self._performance_scope = (
            portfolio_id,
            tenant_id.value,
            start_date,
            end_date,
            as_of_date,
            tuple(sorted(security_ids or [])),
            tuple(sorted(transaction_types or [])),
        )
        self._performance_window = rows
        material = []
        for row in rows:
            payload = asdict(row)
            evidence = row.fx_pnl_source_evidence
            if evidence is not None and evidence.source_evidence is not None:
                payload["fx_pnl_source_evidence"]["source_evidence"] = (
                    evidence.source_evidence.model_dump(mode="python")
                )
            material.append(payload)
        return cast(
            str,
            canonical_content_hash(
                {
                    "scope": self._performance_scope,
                    "portfolio_base_currency": portfolio_base_currency,
                    "matching_window": material,
                }
            ),
        )

    async def _fx_source_evidence(
        self, transactions: list[Transaction], *, portfolio_id: str, tenant_id: TenantId
    ) -> dict[str, FxPnlSourceEvidence]:
        fx_transactions = [
            row
            for row in transactions
            if row.transaction_type in FX_SOURCE_ADMISSION_TYPES
            and row.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
        ]
        if not fx_transactions:
            return {}
        proofs = await SqlAlchemyTransactionSourceEvidence(self._session).read(
            tenant_id=tenant_id.value,
            portfolio_id=portfolio_id,
            transaction_ids=[row.transaction_id for row in fx_transactions],
            consumer="core-qcp",
        )
        return {
            transaction_id: FxPnlSourceEvidence(
                proof.realized_fx_pnl_local,
                proof.realized_fx_pnl_base,
                "FX_SOURCE_AUTHORITY_UNAVAILABLE"
                if proof.status == "UNAVAILABLE"
                else "FX_SOURCE_INCOMPLETE"
                if proof.status == "INCOMPLETE"
                else "FX_SOURCE_QUALIFIED",
                proof,
            )
            for transaction_id, proof in proofs.items()
        }

    async def portfolio_exists(self, portfolio_id: str, *, tenant_id: TenantId) -> bool:
        stmt = (
            select(Portfolio.portfolio_id)
            .where(
                Portfolio.portfolio_id == portfolio_id,
                Portfolio.tenant_id == tenant_id.value,
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def get_portfolio_base_currency(
        self, portfolio_id: str, *, tenant_id: TenantId
    ) -> str | None:
        stmt = (
            select(Portfolio.base_currency)
            .where(
                Portfolio.portfolio_id == portfolio_id,
                Portfolio.tenant_id == tenant_id.value,
            )
            .limit(1)
        )
        return cast(str | None, (await self._session.execute(stmt)).scalar_one_or_none())

    async def list_transaction_cost_evidence(
        self,
        *,
        portfolio_id: str,
        tenant_id: TenantId,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None = None,
        transaction_types: list[str] | None = None,
        curve_keys: list[tuple[str, str, str]] | None = None,
    ) -> list[BookedTransactionEconomics]:
        cost_snapshot = transaction_cost_snapshot_lateral(Transaction.transaction_id)
        stmt = (
            select(
                Transaction,
                cost_snapshot.c.cost_fee_types,
                cost_snapshot.c.cost_amounts,
                cost_snapshot.c.cost_currencies,
                cost_snapshot.c.cost_updated_ats,
            )
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .join(cost_snapshot, true())
            .where(
                Portfolio.tenant_id == tenant_id.value,
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
        return [
            _booked_transaction_economics(
                transaction,
                costs=transaction_cost_snapshots(
                    fee_types=fee_types,
                    amounts=amounts,
                    currencies=currencies,
                    updated_ats=updated_ats,
                ),
            )
            for transaction, fee_types, amounts, currencies, updated_ats in results.all()
        ]

    async def list_transaction_cost_curve_keys(
        self,
        *,
        portfolio_id: str,
        tenant_id: TenantId,
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
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Portfolio.tenant_id == tenant_id.value,
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
        tenant_id: TenantId,
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
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Portfolio.tenant_id == tenant_id.value,
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
        tenant_id: TenantId,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None = None,
        transaction_types: list[str] | None = None,
        after_key: tuple[str, str, str] | tuple[()] = (),
        limit: int | None = None,
    ) -> list[BookedTransactionEconomics]:
        if self._performance_window is not None:
            scope = (
                portfolio_id,
                tenant_id.value,
                start_date,
                end_date,
                as_of_date,
                tuple(sorted(security_ids or [])),
                tuple(sorted(transaction_types or [])),
            )
            if scope != self._performance_scope:
                raise RuntimeError("Performance page scope differs from captured source cut")
            rows = [
                row
                for row in self._performance_window
                if not after_key
                or (
                    row.security_id.strip(),
                    row.transaction_date.date().isoformat(),
                    row.transaction_id,
                )
                > after_key
            ]
            return rows if limit is None else rows[:limit]
        security_order = func.trim(Transaction.security_id).asc()
        transaction_date_order = func.date(Transaction.transaction_date).asc()
        transaction_id_order = Transaction.transaction_id.asc()
        page = (
            select(Transaction.id.label("transaction_pk"))
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Portfolio.tenant_id == tenant_id.value,
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_date >= _start_of_day(start_date),
                Transaction.transaction_date < _start_of_next_day(end_date),
                Transaction.transaction_date < _start_of_next_day(as_of_date),
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
            page = page.where(func.trim(Transaction.security_id).in_(normalized_security_ids))
        if transaction_types:
            page = page.where(Transaction.transaction_type.in_(transaction_types))
        after_predicate = _performance_component_economics_after_key_predicate(after_key)
        if after_predicate is not None:
            page = page.where(after_predicate)
        page = page.order_by(
            security_order,
            transaction_date_order,
            transaction_id_order,
        )
        if limit is not None:
            page = page.limit(limit)
        page = page.subquery("performance_economics_page")

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
        cost_snapshot = transaction_cost_snapshot_lateral(Transaction.transaction_id)
        stmt = (
            select(
                Transaction,
                cost_snapshot.c.cost_fee_types,
                cost_snapshot.c.cost_amounts,
                cost_snapshot.c.cost_currencies,
                cost_snapshot.c.cost_updated_ats,
            )
            .join(page, Transaction.id == page.c.transaction_pk)
            .outerjoin(
                ranked_cashflows,
                and_(
                    ranked_cashflows.c.transaction_id == Transaction.transaction_id,
                    ranked_cashflows.c.rn == 1,
                ),
            )
            .outerjoin(latest_cashflow, latest_cashflow.id == ranked_cashflows.c.id)
            .join(cost_snapshot, true())
            .options(contains_eager(Transaction.cashflow, alias=latest_cashflow))
            .order_by(
                security_order,
                transaction_date_order,
                transaction_id_order,
            )
        )

        results = await self._session.execute(stmt)
        page_rows = results.all()
        fx_evidence = await self._fx_source_evidence(
            [row[0] for row in page_rows], portfolio_id=portfolio_id, tenant_id=tenant_id
        )
        return [
            _booked_transaction_economics(
                transaction,
                fx_pnl_source_evidence=fx_evidence.get(transaction.transaction_id),
                costs=transaction_cost_snapshots(
                    fee_types=fee_types,
                    amounts=amounts,
                    currencies=currencies,
                    updated_ats=updated_ats,
                ),
            )
            for transaction, fee_types, amounts, currencies, updated_ats in page_rows
        ]
