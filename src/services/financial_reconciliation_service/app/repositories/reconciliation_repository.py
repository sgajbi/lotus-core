from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import uuid4

from portfolio_common.database_models import (
    Cashflow,
    CashflowRule,
    DailyPositionSnapshot,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    PortfolioTimeseries,
    PositionTimeseries,
    Transaction,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class ReconciliationRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def create_run(
        self,
        *,
        reconciliation_type: str,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
        requested_by: str | None,
        dedupe_key: str | None,
        correlation_id: str | None,
        tolerance: Decimal | None,
    ) -> tuple[FinancialReconciliationRun, bool]:
        if dedupe_key is not None:
            existing = await self.get_run_by_dedupe_key(dedupe_key)
            if existing is not None:
                return existing, False

        run = FinancialReconciliationRun(
            run_id=f"recon-{uuid4().hex}",
            reconciliation_type=reconciliation_type,
            portfolio_id=portfolio_id,
            business_date=business_date,
            epoch=epoch,
            requested_by=requested_by,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id,
            tolerance=tolerance,
            status="RUNNING",
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
                FinancialReconciliationRun.dedupe_key == dedupe_key
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
            select(FinancialReconciliationRun).where(FinancialReconciliationRun.run_id == run_id)
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        *,
        reconciliation_type: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 50,
    ) -> list[FinancialReconciliationRun]:
        stmt = select(FinancialReconciliationRun)
        if reconciliation_type is not None:
            stmt = stmt.where(FinancialReconciliationRun.reconciliation_type == reconciliation_type)
        if portfolio_id is not None:
            stmt = stmt.where(FinancialReconciliationRun.portfolio_id == portfolio_id)
        stmt = stmt.order_by(FinancialReconciliationRun.started_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_findings(self, run_id: str) -> list[FinancialReconciliationFinding]:
        result = await self.db.execute(
            select(FinancialReconciliationFinding)
            .where(FinancialReconciliationFinding.run_id == run_id)
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
            .join(CashflowRule, CashflowRule.transaction_type == Transaction.transaction_type)
            .outerjoin(Cashflow, Cashflow.transaction_id == Transaction.transaction_id)
        )
        if portfolio_id is not None:
            stmt = stmt.where(Transaction.portfolio_id == portfolio_id)
        if business_date is not None:
            stmt = stmt.where(func.date(Transaction.transaction_date) == business_date)
        result = await self.db.execute(stmt.order_by(Transaction.transaction_id.asc()))
        return result.all()

    async def fetch_position_valuation_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> list[DailyPositionSnapshot]:
        stmt = select(DailyPositionSnapshot).where(
            DailyPositionSnapshot.market_price.is_not(None),
            DailyPositionSnapshot.market_value_local.is_not(None),
            DailyPositionSnapshot.cost_basis_local.is_not(None),
            DailyPositionSnapshot.unrealized_gain_loss_local.is_not(None),
        )
        if portfolio_id is not None:
            stmt = stmt.where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        if business_date is not None:
            stmt = stmt.where(DailyPositionSnapshot.date == business_date)
        if epoch is not None:
            stmt = stmt.where(DailyPositionSnapshot.epoch == epoch)
        result = await self.db.execute(
            stmt.order_by(
                DailyPositionSnapshot.portfolio_id.asc(),
                DailyPositionSnapshot.security_id.asc(),
                DailyPositionSnapshot.date.asc(),
                DailyPositionSnapshot.epoch.asc(),
            )
        )
        return list(result.scalars().all())

    async def fetch_portfolio_timeseries_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> list[PortfolioTimeseries]:
        stmt = select(PortfolioTimeseries)
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
        stmt = select(
            PositionTimeseries.portfolio_id,
            PositionTimeseries.date,
            PositionTimeseries.epoch,
            func.count().label("position_row_count"),
            func.sum(PositionTimeseries.bod_market_value).label("bod_market_value"),
            func.sum(
                PositionTimeseries.bod_cashflow_position + PositionTimeseries.bod_cashflow_portfolio
            ).label("bod_cashflow"),
            func.sum(
                PositionTimeseries.eod_cashflow_position + PositionTimeseries.eod_cashflow_portfolio
            ).label("eod_cashflow"),
            func.sum(PositionTimeseries.eod_market_value).label("eod_market_value"),
            func.sum(PositionTimeseries.fees).label("fees"),
        ).group_by(
            PositionTimeseries.portfolio_id,
            PositionTimeseries.date,
            PositionTimeseries.epoch,
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
        stmt = select(
            DailyPositionSnapshot.portfolio_id,
            DailyPositionSnapshot.date,
            DailyPositionSnapshot.epoch,
            func.count().label("snapshot_count"),
        ).group_by(
            DailyPositionSnapshot.portfolio_id,
            DailyPositionSnapshot.date,
            DailyPositionSnapshot.epoch,
        )
        if portfolio_id is not None:
            stmt = stmt.where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        if business_date is not None:
            stmt = stmt.where(DailyPositionSnapshot.date == business_date)
        if epoch is not None:
            stmt = stmt.where(DailyPositionSnapshot.epoch == epoch)
        result = await self.db.execute(stmt)
        return result.all()
