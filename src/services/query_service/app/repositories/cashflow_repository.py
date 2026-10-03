# src/services/query_service/app/repositories/cashflow_repository.py
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple, cast

from portfolio_common.business_calendar_sql import business_calendar_code_matches
from portfolio_common.cashflow_source_cut_models import PortfolioCashflowSourceCut
from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    Cashflow,
    Portfolio,
    PositionState,
    Transaction,
)
from portfolio_common.database_models import (
    FxRate as FxRateModel,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction.type_registry import INCOME_RECOGNITION_TRANSACTION_TYPES
from portfolio_common.infrastructure.persistence.statement_batching import (
    StatementBatchOperation,
    iter_statement_chunks,
    observe_multi_statement_batch,
)
from portfolio_common.utils import async_timed
from sqlalchemy import and_, case, exists, func, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from .date_filters import start_of_day, start_of_next_day
from .identifier_normalization import normalize_security_id
from .portfolio_existence import portfolio_exists_for_tenant

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CashflowSeriesEvidence:
    rows: list[tuple[date, str, Decimal]]
    latest_evidence_timestamp: datetime | None
    source_row_count: int = 0
    source_currency_totals: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class CashflowFxRateEvidence:
    source_id: int
    from_currency: str
    to_currency: str
    rate_date: date
    rate: Decimal
    source_updated_at: datetime

    def lineage_payload(self) -> dict[str, int | str]:
        return {
            "source_id": self.source_id,
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "rate_date": self.rate_date.isoformat(),
            "rate": str(self.rate),
            "source_updated_at": self.source_updated_at.isoformat(),
            "selection_policy": "EXACT_DATE_DIRECT_PAIR",
        }


CashflowAggregateRow = tuple[date, str, Decimal, int, Decimal, datetime | None]


def _cashflow_series_evidence(rows: list[CashflowAggregateRow]) -> CashflowSeriesEvidence:
    normalized_rows: list[tuple[date, str, Decimal]] = []
    latest_evidence_timestamp: datetime | None = None
    source_row_count = 0
    source_currency_totals: dict[str, Decimal] = {}
    for row in rows:
        flow_date, currency, amount, row_count, currency_total, timestamp = row
        normalized_currency = normalize_currency_code(str(currency))
        normalized_rows.append((flow_date, normalized_currency, Decimal(str(amount))))
        source_row_count += int(row_count or 0)
        source_currency_totals[normalized_currency] = Decimal(str(currency_total or 0))
        if timestamp is not None and (
            latest_evidence_timestamp is None or timestamp > latest_evidence_timestamp
        ):
            latest_evidence_timestamp = timestamp
    return CashflowSeriesEvidence(
        rows=normalized_rows,
        latest_evidence_timestamp=latest_evidence_timestamp,
        source_row_count=source_row_count,
        source_currency_totals=source_currency_totals,
    )


CashMovementSummaryRow = tuple[str, str, str, bool, bool, int, Decimal, datetime | None]


@dataclass(frozen=True)
class CashMovementSummaryEvidence:
    rows: list[CashMovementSummaryRow]
    source_row_count: int
    source_currency_totals: dict[str, Decimal]


@dataclass(frozen=True)
class CashflowSourceCutEvidence:
    """Source-owned facts that identify one portfolio cashflow evidence cut.

    The product-specific windows intentionally do not contribute to this identity.
    A common cut instead names the admitted portfolio's source state as of one
    governed business date, allowing two products with different output windows
    to make a truthful coherence claim.
    """

    portfolio_base_currency: str
    cashflow_revision_count: int
    cashflow_revision_digest: str
    settlement_revision_count: int
    settlement_revision_digest: str
    materialized_at: datetime


class CashflowRepository:
    """
    Handles read-only database queries for cashflow data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def establish_cashflow_source_read_snapshot(self) -> None:
        """Make response evidence and its source cut share one read-only snapshot."""
        if self.db.in_transaction():
            raise RuntimeError(
                "Cashflow source snapshot must be established before the first database read."
            )
        await self.db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))

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

    async def portfolio_exists(self, portfolio_id: str, *, tenant_id: TenantId) -> bool:
        """Whether the admitted tenant owns this portfolio.

        Delegates so the predicate lives in one place; see
        :mod:`portfolio_existence`.
        """
        return cast(
            bool,
            await portfolio_exists_for_tenant(self.db, portfolio_id, tenant_id=tenant_id),
        )

    async def get_portfolio_currency(self, portfolio_id: str, *, tenant_id: TenantId) -> str | None:
        """The base currency of a portfolio the admitted tenant owns.

        Scoped for the same reason as the existence gate: this is the first read
        on the cash-movement and cashflow-projection paths, and an unscoped
        answer here lets the rest of the request proceed on a foreign portfolio.
        """
        stmt = (
            select(Portfolio.base_currency)
            .where(
                Portfolio.portfolio_id == portfolio_id,
                Portfolio.tenant_id == tenant_id.value,
            )
            .limit(1)
        )
        return cast(str | None, (await self.db.execute(stmt)).scalar_one_or_none())

    async def get_latest_business_date(self) -> Optional[date]:
        stmt = select(func.max(BusinessDate.date)).where(
            business_calendar_code_matches(
                BusinessDate.calendar_code, DEFAULT_BUSINESS_CALENDAR_CODE
            )
        )
        return cast(date | None, (await self.db.execute(stmt)).scalar_one_or_none())

    async def get_portfolio_cashflow_series_with_evidence(
        self, portfolio_id: str, start_date: date, end_date: date, *, tenant_id: TenantId
    ) -> CashflowSeriesEvidence:
        """Return booked cashflows grouped in their authoritative native currency."""
        latest_cashflows = self._latest_cashflows_subquery(portfolio_id=portfolio_id)
        stmt = (
            select(
                latest_cashflows.c.cashflow_date,
                latest_cashflows.c.currency,
                func.sum(latest_cashflows.c.amount).label("net_amount"),
                func.count().label("source_row_count"),
                func.sum(func.sum(latest_cashflows.c.amount))
                .over(partition_by=latest_cashflows.c.currency)
                .label("source_currency_total"),
                func.max(latest_cashflows.c.updated_at).label("latest_evidence_timestamp"),
            )
            .join(Portfolio, Portfolio.portfolio_id == latest_cashflows.c.portfolio_id)
            .where(
                latest_cashflows.c.portfolio_id == portfolio_id,
                Portfolio.tenant_id == tenant_id.value,
                latest_cashflows.c.cashflow_date.between(start_date, end_date),
                latest_cashflows.c.is_portfolio_flow,
            )
            .group_by(latest_cashflows.c.cashflow_date, latest_cashflows.c.currency)
            .order_by(latest_cashflows.c.cashflow_date.asc(), latest_cashflows.c.currency.asc())
        )
        rows = cast(list[CashflowAggregateRow], (await self.db.execute(stmt)).all())
        return _cashflow_series_evidence(rows)

    async def get_projected_settlement_cashflow_series_with_evidence(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        *,
        tenant_id: TenantId,
    ) -> CashflowSeriesEvidence:
        """Return unbooked settlement cashflows in authoritative trade currency."""
        # `settlement_date` is an instant.  This product publishes UTC event-date
        # buckets; booking-centre business dates require an explicit separate
        # authority and must not follow the database session's TimeZone.
        settlement_date = func.date(func.timezone("UTC", Transaction.settlement_date))
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
                Transaction.trade_currency,
                func.sum(signed_amount).label("net_amount"),
                func.count().label("source_row_count"),
                func.sum(func.sum(signed_amount))
                .over(partition_by=Transaction.trade_currency)
                .label("source_currency_total"),
                func.max(Transaction.updated_at).label("latest_evidence_timestamp"),
            )
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Portfolio.tenant_id == tenant_id.value,
                Transaction.transaction_type.in_(("DEPOSIT", "WITHDRAWAL")),
                Transaction.settlement_date.is_not(None),
                Transaction.settlement_date >= start_of_day(start_date),
                Transaction.settlement_date < start_of_next_day(end_date),
                Transaction.transaction_date < start_of_day(start_date),
                ~exists(select(1).where(Cashflow.transaction_id == Transaction.transaction_id)),
            )
            .group_by(settlement_date, Transaction.trade_currency)
            .order_by(settlement_date.asc(), Transaction.trade_currency.asc())
        )
        rows = cast(list[CashflowAggregateRow], (await self.db.execute(stmt)).all())
        return _cashflow_series_evidence(rows)

    async def get_cashflow_fx_rate_evidence(
        self,
        *,
        required_conversions: set[tuple[str, str, date]],
    ) -> dict[tuple[str, str, date], CashflowFxRateEvidence]:
        """Resolve exact-date direct FX evidence for a bounded cashflow window in one read."""
        normalized = {
            (
                normalize_currency_code(from_currency),
                normalize_currency_code(to_currency),
                rate_date,
            )
            for from_currency, to_currency, rate_date in required_conversions
            if normalize_currency_code(from_currency) != normalize_currency_code(to_currency)
        }
        if not normalized:
            return {}
        from_currency_expr = func.upper(func.trim(FxRateModel.from_currency))
        to_currency_expr = func.upper(func.trim(FxRateModel.to_currency))
        normalized_keys = sorted(normalized)
        observe_multi_statement_batch(
            operation=StatementBatchOperation.CASHFLOW_FX_LOOKUP,
            item_count=len(normalized_keys),
            binds_per_row=3,
        )
        evidence: dict[tuple[str, str, date], CashflowFxRateEvidence] = {}
        for chunk in iter_statement_chunks(normalized_keys, binds_per_row=3):
            stmt = (
                select(
                    FxRateModel.id,
                    from_currency_expr,
                    to_currency_expr,
                    FxRateModel.rate_date,
                    FxRateModel.rate,
                    FxRateModel.updated_at,
                )
                .where(
                    tuple_(from_currency_expr, to_currency_expr, FxRateModel.rate_date).in_(chunk)
                )
                .order_by(
                    FxRateModel.rate_date.asc(),
                    from_currency_expr.asc(),
                    to_currency_expr.asc(),
                    FxRateModel.id.asc(),
                )
            )
            rows = (await self.db.execute(stmt)).all()
            for row in rows:
                source_id, from_currency, to_currency, rate_date, rate, source_updated_at = row
                key = (str(from_currency), str(to_currency), rate_date)
                evidence[key] = CashflowFxRateEvidence(
                    source_id=int(source_id),
                    from_currency=str(from_currency),
                    to_currency=str(to_currency),
                    rate_date=rate_date,
                    rate=Decimal(str(rate)),
                    source_updated_at=source_updated_at,
                )
        return evidence

    @async_timed(repository="CashflowRepository", method="get_portfolio_cash_movement_summary")
    async def get_portfolio_cash_movement_summary(
        self, portfolio_id: str, start_date: date, end_date: date, *, tenant_id: TenantId
    ) -> CashMovementSummaryEvidence:
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
                func.sum(func.count()).over().label("source_row_count"),
                func.sum(func.sum(latest_cashflows.c.amount))
                .over(partition_by=latest_cashflows.c.currency)
                .label("source_currency_total"),
            )
            .join(Portfolio, Portfolio.portfolio_id == latest_cashflows.c.portfolio_id)
            .where(
                latest_cashflows.c.portfolio_id == portfolio_id,
                Portfolio.tenant_id == tenant_id.value,
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
        rows = (await self.db.execute(stmt)).all()
        return CashMovementSummaryEvidence(
            rows=[
                (
                    str(row[0]),
                    str(row[1]),
                    str(row[2]),
                    bool(row[3]),
                    bool(row[4]),
                    int(row[5] or 0),
                    Decimal(str(row[6] or 0)),
                    row[7],
                )
                for row in rows
            ],
            source_row_count=int(rows[0][8] or 0) if rows else 0,
            source_currency_totals={str(row[2]): Decimal(str(row[9] or 0)) for row in rows},
        )

    async def get_cashflow_source_cut_evidence(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        tenant_id: TenantId,
    ) -> CashflowSourceCutEvidence:
        """Read the admitted portfolio's complete stable evidence state.

        ``as_of_date`` is part of the public cut identity assembled by the caller,
        not a source-membership filter: projections can include future booked or
        settled cashflows that still need to change the same source cut.
        """
        del as_of_date
        evidence = (
            await self.db.execute(
                select(
                    PortfolioCashflowSourceCut.portfolio_base_currency,
                    PortfolioCashflowSourceCut.cashflow_revision_count,
                    PortfolioCashflowSourceCut.cashflow_revision_digest,
                    PortfolioCashflowSourceCut.settlement_revision_count,
                    PortfolioCashflowSourceCut.settlement_revision_digest,
                    PortfolioCashflowSourceCut.materialized_at,
                )
                .join(
                    Portfolio,
                    Portfolio.portfolio_id == PortfolioCashflowSourceCut.portfolio_id,
                )
                .where(
                    PortfolioCashflowSourceCut.portfolio_id == portfolio_id,
                    Portfolio.tenant_id == tenant_id.value,
                )
            )
        ).one_or_none()
        if evidence is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")
        return CashflowSourceCutEvidence(
            portfolio_base_currency=str(evidence[0]),
            cashflow_revision_count=int(evidence[1]),
            cashflow_revision_digest=str(evidence[2]),
            settlement_revision_count=int(evidence[3]),
            settlement_revision_digest=str(evidence[4]),
            materialized_at=evidence[5],
        )

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
        return cast(List[Tuple[date, Decimal]], result.all())

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
            .join(Transaction, Transaction.transaction_id == Cashflow.transaction_id)
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
                Transaction.transaction_type.in_(sorted(INCOME_RECOGNITION_TRANSACTION_TYPES)),
            )
        )
        result = await self.db.execute(stmt)
        return cast(List[Cashflow], result.scalars().all())
