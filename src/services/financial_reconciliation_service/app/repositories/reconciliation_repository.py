from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

from portfolio_common.database_models import (
    Cashflow,
    CashflowRule,
    DailyPositionSnapshot,
    DailyPositionValuationReceiptRecord,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    FxRate,
    Instrument,
    Portfolio,
    PortfolioTimeseries,
    PositionTimeseries,
    Transaction,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.tenant import TenantId
from portfolio_common.infrastructure.persistence.statement_batching import (
    StatementBatchOperation,
    iter_statement_chunks,
    observe_multi_statement_batch,
)
from portfolio_common.logging_utils import normalize_lineage_value
from sqlalchemy import Date, String, and_, column, func, select, true, values
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.reconciliation_run_lifecycle_policy import initial_reconciliation_run_status
from ..ports.reconciliation_repository_ports import FxRateLookupKey


def _latest_fx_rates_statement(keys: Sequence[FxRateLookupKey]):
    lookup_rows = values(
        column("from_currency", String(3)),
        column("to_currency", String(3)),
        column("business_date", Date()),
        name="fx_lookup",
    ).data([(key.from_currency, key.to_currency, key.business_date) for key in keys])
    latest_rate = (
        select(FxRate.rate.label("rate"))
        .where(
            func.upper(func.trim(FxRate.from_currency)) == lookup_rows.c.from_currency,
            func.upper(func.trim(FxRate.to_currency)) == lookup_rows.c.to_currency,
            FxRate.rate_date <= lookup_rows.c.business_date,
        )
        .order_by(FxRate.rate_date.desc(), FxRate.id.desc())
        .limit(1)
        .lateral("latest_fx_rate")
    )
    return (
        select(
            lookup_rows.c.from_currency,
            lookup_rows.c.to_currency,
            lookup_rows.c.business_date,
            latest_rate.c.rate,
        )
        .select_from(lookup_rows.outerjoin(latest_rate, true()))
        .order_by(
            lookup_rows.c.from_currency,
            lookup_rows.c.to_currency,
            lookup_rows.c.business_date,
        )
    )


class ReconciliationRepository:
    def __init__(
        self,
        db_session: AsyncSession,
        *,
        tenant_id: str,
        run_id_suffix_provider: Callable[[], str] | None = None,
    ):
        self.db = db_session
        self._tenant_id = TenantId(tenant_id).value
        self._run_id_suffix_provider = run_id_suffix_provider or (lambda: uuid4().hex)

    async def create_run(
        self,
        *,
        reconciliation_type: str,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
        aggregation_revision: int | None,
        requested_by: str | None,
        dedupe_key: str | None,
        correlation_id: str | None,
        tolerance: Decimal | None,
    ) -> tuple[FinancialReconciliationRun, bool]:
        correlation_id = normalize_lineage_value(correlation_id)
        if portfolio_id is not None:
            await self._ensure_portfolio_owned(portfolio_id)
        if dedupe_key is not None:
            existing = await self.get_run_by_dedupe_key(dedupe_key)
            if existing is not None:
                return existing, False

        run = FinancialReconciliationRun(
            run_id=f"recon-{self._run_id_suffix_provider()}",
            tenant_id=self._tenant_id,
            reconciliation_type=reconciliation_type,
            portfolio_id=portfolio_id,
            business_date=business_date,
            epoch=epoch,
            aggregation_revision=aggregation_revision,
            requested_by=requested_by,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id,
            tolerance=tolerance,
            status=initial_reconciliation_run_status(),
        )
        try:
            async with self.db.begin_nested():
                self.db.add(run)
                await self.db.flush()
        except IntegrityError:
            if dedupe_key is None:
                raise
            existing = await self.get_run_by_dedupe_key(dedupe_key)
            if existing is None:
                raise
            return existing, False
        await self.db.refresh(run)
        return run, True

    async def get_run_by_dedupe_key(
        self,
        dedupe_key: str,
    ) -> FinancialReconciliationRun | None:
        result = await self.db.execute(
            select(FinancialReconciliationRun).where(
                FinancialReconciliationRun.tenant_id == self._tenant_id,
                FinancialReconciliationRun.dedupe_key == dedupe_key,
            )
        )
        return result.scalar_one_or_none()

    async def add_findings(self, findings: Sequence[FinancialReconciliationFinding]) -> None:
        self.db.add_all(list(findings))
        await self.db.flush()

    async def mark_run_completed(
        self,
        run: FinancialReconciliationRun,
        *,
        status: str,
        summary: dict,
        failure_reason: str | None = None,
    ) -> None:
        run.status = status
        run.summary = summary
        run.failure_reason = failure_reason
        run.completed_at = func.now()
        await self.db.flush()
        await self.db.refresh(run)

    async def get_run(self, run_id: str) -> FinancialReconciliationRun | None:
        result = await self.db.execute(
            select(FinancialReconciliationRun).where(
                FinancialReconciliationRun.tenant_id == self._tenant_id,
                FinancialReconciliationRun.run_id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        *,
        reconciliation_type: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 50,
    ) -> list[FinancialReconciliationRun]:
        stmt = select(FinancialReconciliationRun).where(
            FinancialReconciliationRun.tenant_id == self._tenant_id
        )
        if reconciliation_type is not None:
            stmt = stmt.where(FinancialReconciliationRun.reconciliation_type == reconciliation_type)
        if portfolio_id is not None:
            stmt = stmt.where(FinancialReconciliationRun.portfolio_id == portfolio_id)
        stmt = stmt.order_by(
            FinancialReconciliationRun.started_at.desc(),
            FinancialReconciliationRun.id.desc(),
        ).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_findings(self, run_id: str) -> list[FinancialReconciliationFinding]:
        result = await self.db.execute(
            select(FinancialReconciliationFinding)
            .join(
                FinancialReconciliationRun,
                FinancialReconciliationRun.run_id == FinancialReconciliationFinding.run_id,
            )
            .where(FinancialReconciliationFinding.run_id == run_id)
            .where(FinancialReconciliationRun.tenant_id == self._tenant_id)
            .order_by(
                FinancialReconciliationFinding.severity.asc(),
                FinancialReconciliationFinding.finding_type.asc(),
                FinancialReconciliationFinding.id.asc(),
            )
        )
        return list(result.scalars().all())

    async def fetch_transaction_cashflow_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
    ):
        stmt = (
            select(Transaction, CashflowRule, Cashflow)
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .join(CashflowRule, CashflowRule.transaction_type == Transaction.transaction_type)
            .outerjoin(Cashflow, Cashflow.transaction_id == Transaction.transaction_id)
            .where(Portfolio.tenant_id == self._tenant_id)
        )
        if portfolio_id is not None:
            stmt = stmt.where(Transaction.portfolio_id == portfolio_id)
        if business_date is not None:
            stmt = stmt.where(
                Transaction.transaction_date >= datetime.combine(business_date, time.min),
                Transaction.transaction_date
                < datetime.combine(business_date + timedelta(days=1), time.min),
            )
        result = await self.db.execute(stmt.order_by(Transaction.transaction_id.asc()))
        return result.all()

    async def fetch_position_valuation_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ):
        instrument_security_id = func.trim(Instrument.security_id)
        snapshot_security_id = func.trim(DailyPositionSnapshot.security_id)
        ranked_snapshot_rows = None
        if business_date is not None and epoch is not None:
            ranked_snapshot_rows = select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=(
                        DailyPositionSnapshot.portfolio_id,
                        snapshot_security_id,
                    ),
                    order_by=(DailyPositionSnapshot.epoch.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            ).where(
                DailyPositionSnapshot.date == business_date,
                DailyPositionSnapshot.epoch <= epoch,
            )
            if portfolio_id is not None:
                ranked_snapshot_rows = ranked_snapshot_rows.where(
                    DailyPositionSnapshot.portfolio_id == portfolio_id
                )
            ranked_snapshot_rows = ranked_snapshot_rows.subquery()
        stmt = (
            select(
                DailyPositionSnapshot,
                Instrument,
                Portfolio,
                DailyPositionValuationReceiptRecord,
            )
            .join(Instrument, instrument_security_id == snapshot_security_id)
            .join(Portfolio, Portfolio.portfolio_id == DailyPositionSnapshot.portfolio_id)
            .outerjoin(
                DailyPositionValuationReceiptRecord,
                DailyPositionValuationReceiptRecord.snapshot_id == DailyPositionSnapshot.id,
            )
            .where(
                Portfolio.tenant_id == self._tenant_id,
                DailyPositionSnapshot.market_price.is_not(None),
                DailyPositionSnapshot.market_value_local.is_not(None),
                DailyPositionSnapshot.cost_basis_local.is_not(None),
                DailyPositionSnapshot.unrealized_gain_loss_local.is_not(None),
            )
        )
        if ranked_snapshot_rows is not None:
            stmt = stmt.join(
                ranked_snapshot_rows,
                DailyPositionSnapshot.id == ranked_snapshot_rows.c.snapshot_id,
            ).where(ranked_snapshot_rows.c.rn == 1)
        elif portfolio_id is not None:
            stmt = stmt.where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        if business_date is not None and ranked_snapshot_rows is None:
            stmt = stmt.where(DailyPositionSnapshot.date == business_date)
        if epoch is not None and ranked_snapshot_rows is None:
            stmt = stmt.where(DailyPositionSnapshot.epoch == epoch)
        result = await self.db.execute(
            stmt.order_by(
                DailyPositionSnapshot.portfolio_id.asc(),
                DailyPositionSnapshot.security_id.asc(),
                DailyPositionSnapshot.date.asc(),
                DailyPositionSnapshot.epoch.asc(),
            )
        )
        return result.all()

    async def fetch_portfolio_timeseries_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> list[PortfolioTimeseries]:
        stmt = (
            select(PortfolioTimeseries)
            .join(Portfolio, Portfolio.portfolio_id == PortfolioTimeseries.portfolio_id)
            .where(Portfolio.tenant_id == self._tenant_id)
        )
        if portfolio_id is not None:
            stmt = stmt.where(PortfolioTimeseries.portfolio_id == portfolio_id)
        if business_date is not None:
            stmt = stmt.where(PortfolioTimeseries.date == business_date)
        if epoch is not None:
            stmt = stmt.where(PortfolioTimeseries.epoch == epoch)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def fetch_position_timeseries_aggregates(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ):
        stmt = (
            select(
                PositionTimeseries.portfolio_id,
                PositionTimeseries.date,
                PositionTimeseries.epoch,
                func.count().label("position_row_count"),
                func.sum(PositionTimeseries.bod_market_value).label("bod_market_value"),
                func.sum(
                    PositionTimeseries.bod_cashflow_position
                    + PositionTimeseries.bod_cashflow_portfolio
                ).label("bod_cashflow"),
                func.sum(
                    PositionTimeseries.eod_cashflow_position
                    + PositionTimeseries.eod_cashflow_portfolio
                ).label("eod_cashflow"),
                func.sum(PositionTimeseries.eod_market_value).label("eod_market_value"),
                func.sum(PositionTimeseries.fees).label("fees"),
            )
            .join(Portfolio, Portfolio.portfolio_id == PositionTimeseries.portfolio_id)
            .where(Portfolio.tenant_id == self._tenant_id)
            .group_by(
                PositionTimeseries.portfolio_id,
                PositionTimeseries.date,
                PositionTimeseries.epoch,
            )
        )
        if portfolio_id is not None:
            stmt = stmt.where(PositionTimeseries.portfolio_id == portfolio_id)
        if business_date is not None:
            stmt = stmt.where(PositionTimeseries.date == business_date)
        if epoch is not None:
            stmt = stmt.where(PositionTimeseries.epoch == epoch)
        result = await self.db.execute(stmt)
        return result.all()

    async def fetch_snapshot_counts(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ):
        stmt = (
            select(
                DailyPositionSnapshot.portfolio_id,
                DailyPositionSnapshot.date,
                DailyPositionSnapshot.epoch,
                func.count().label("snapshot_count"),
            )
            .join(Portfolio, Portfolio.portfolio_id == DailyPositionSnapshot.portfolio_id)
            .where(Portfolio.tenant_id == self._tenant_id)
            .group_by(
                DailyPositionSnapshot.portfolio_id,
                DailyPositionSnapshot.date,
                DailyPositionSnapshot.epoch,
            )
        )
        if portfolio_id is not None:
            stmt = stmt.where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        if business_date is not None:
            stmt = stmt.where(DailyPositionSnapshot.date == business_date)
        if epoch is not None:
            stmt = stmt.where(DailyPositionSnapshot.epoch == epoch)
        result = await self.db.execute(stmt)
        return result.all()

    async def fetch_authoritative_position_timeseries_rows(
        self,
        *,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ):
        instrument_security_id = func.trim(Instrument.security_id)
        position_timeseries_security_id = func.trim(PositionTimeseries.security_id)
        ranked_position_rows = (
            select(
                PositionTimeseries.portfolio_id.label("portfolio_id"),
                PositionTimeseries.security_id.label("security_id"),
                PositionTimeseries.date.label("date"),
                PositionTimeseries.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=(PositionTimeseries.security_id,),
                    order_by=(PositionTimeseries.date.desc(), PositionTimeseries.epoch.desc()),
                )
                .label("rn"),
            )
            .where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.date <= business_date,
                PositionTimeseries.epoch <= epoch,
            )
            .subquery()
        )

        stmt = (
            select(PositionTimeseries, Instrument, Portfolio)
            .join(
                ranked_position_rows,
                and_(
                    PositionTimeseries.portfolio_id == ranked_position_rows.c.portfolio_id,
                    PositionTimeseries.security_id == ranked_position_rows.c.security_id,
                    PositionTimeseries.date == ranked_position_rows.c.date,
                    PositionTimeseries.epoch == ranked_position_rows.c.epoch,
                ),
            )
            .join(Instrument, instrument_security_id == position_timeseries_security_id)
            .join(Portfolio, Portfolio.portfolio_id == PositionTimeseries.portfolio_id)
            .where(
                Portfolio.tenant_id == self._tenant_id,
                ranked_position_rows.c.rn == 1,
            )
            .order_by(PositionTimeseries.security_id.asc())
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def fetch_authoritative_snapshot_count(
        self,
        *,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ) -> int:
        ranked_snapshot_rows = (
            select(
                DailyPositionSnapshot.security_id.label("security_id"),
                DailyPositionSnapshot.date.label("date"),
                DailyPositionSnapshot.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=(DailyPositionSnapshot.security_id,),
                    order_by=(
                        DailyPositionSnapshot.date.desc(),
                        DailyPositionSnapshot.epoch.desc(),
                    ),
                )
                .label("rn"),
            )
            .join(Portfolio, Portfolio.portfolio_id == DailyPositionSnapshot.portfolio_id)
            .where(
                Portfolio.tenant_id == self._tenant_id,
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= business_date,
                DailyPositionSnapshot.epoch <= epoch,
            )
            .subquery()
        )
        stmt = (
            select(func.count())
            .select_from(ranked_snapshot_rows)
            .where(ranked_snapshot_rows.c.rn == 1)
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def _ensure_portfolio_owned(self, portfolio_id: str) -> None:
        result = await self.db.execute(
            select(Portfolio.portfolio_id)
            .where(
                Portfolio.tenant_id == self._tenant_id,
                Portfolio.portfolio_id == portfolio_id,
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is None:
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

    async def fetch_latest_fx_rates(
        self,
        *,
        keys: Sequence[FxRateLookupKey],
    ) -> dict[FxRateLookupKey, Decimal | None]:
        normalized_keys = sorted(
            {
                FxRateLookupKey(
                    from_currency=normalize_currency_code(key.from_currency),
                    to_currency=normalize_currency_code(key.to_currency),
                    business_date=key.business_date,
                )
                for key in keys
            }
        )
        if not normalized_keys:
            return {}
        observe_multi_statement_batch(
            operation=StatementBatchOperation.FINANCIAL_RECONCILIATION_FX_LOOKUP,
            item_count=len(normalized_keys),
            binds_per_row=3,
            reserved_binds=1,
        )
        rates: dict[FxRateLookupKey, Decimal | None] = {}
        for chunk in iter_statement_chunks(
            normalized_keys,
            binds_per_row=3,
            reserved_binds=1,
        ):
            result = await self.db.execute(_latest_fx_rates_statement(chunk))
            for from_currency, to_currency, business_date, rate in result.all():
                rates[
                    FxRateLookupKey(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        business_date=business_date,
                    )
                ] = rate
        return rates
