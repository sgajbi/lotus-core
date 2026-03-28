from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    Portfolio,
    PositionState,
    Transaction,
)
from sqlalchemy import String, and_, case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from .date_filters import start_of_day, start_of_next_day


@dataclass(frozen=True)
class ReportingSnapshotRow:
    portfolio: Portfolio
    snapshot: DailyPositionSnapshot
    instrument: Instrument | None


@dataclass(frozen=True)
class IncomeSummaryAggregateRow:
    portfolio_id: str
    booking_center_code: str
    client_id: str
    portfolio_currency: str
    source_currency: str
    income_type: str
    requested_transaction_count: int
    ytd_transaction_count: int
    requested_gross_amount: Decimal
    ytd_gross_amount: Decimal
    requested_withholding_tax: Decimal
    ytd_withholding_tax: Decimal
    requested_other_deductions: Decimal
    ytd_other_deductions: Decimal
    requested_net_amount: Decimal
    ytd_net_amount: Decimal


@dataclass(frozen=True)
class ActivitySummaryAggregateRow:
    portfolio_id: str
    booking_center_code: str
    client_id: str
    portfolio_currency: str
    source_currency: str
    bucket: str
    requested_transaction_count: int
    ytd_transaction_count: int
    requested_amount: Decimal
    ytd_amount: Decimal


class ReportingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_latest_business_date(self) -> date | None:
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_portfolio_by_id(self, portfolio_id: str) -> Portfolio | None:
        stmt = select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_portfolios(
        self,
        *,
        portfolio_id: str | None = None,
        portfolio_ids: list[str] | None = None,
        client_id: str | None = None,
        booking_center_code: str | None = None,
    ) -> list[Portfolio]:
        stmt = select(Portfolio)
        if portfolio_id:
            stmt = stmt.where(Portfolio.portfolio_id == portfolio_id)
        if portfolio_ids:
            stmt = stmt.where(Portfolio.portfolio_id.in_(portfolio_ids))
        if client_id:
            stmt = stmt.where(Portfolio.client_id == client_id)
        if booking_center_code:
            stmt = stmt.where(Portfolio.booking_center_code == booking_center_code)
        stmt = stmt.order_by(Portfolio.portfolio_id.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_latest_snapshot_rows(
        self,
        *,
        portfolio_ids: list[str],
        as_of_date: date,
    ) -> list[ReportingSnapshotRow]:
        ranked_snapshot_subq = (
            select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=(
                        DailyPositionSnapshot.portfolio_id,
                        DailyPositionSnapshot.security_id,
                    ),
                    order_by=(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(
                DailyPositionSnapshot.portfolio_id.in_(portfolio_ids),
                DailyPositionSnapshot.date <= as_of_date,
                DailyPositionSnapshot.quantity != 0,
            )
            .subquery()
        )

        stmt = (
            select(Portfolio, DailyPositionSnapshot, Instrument)
            .join(
                ranked_snapshot_subq,
                and_(
                    DailyPositionSnapshot.id == ranked_snapshot_subq.c.snapshot_id,
                    ranked_snapshot_subq.c.rn == 1,
                ),
            )
            .join(Portfolio, Portfolio.portfolio_id == DailyPositionSnapshot.portfolio_id)
            .outerjoin(Instrument, Instrument.security_id == DailyPositionSnapshot.security_id)
            .order_by(
                DailyPositionSnapshot.portfolio_id.asc(),
                DailyPositionSnapshot.security_id.asc(),
            )
        )

        rows = (await self.db.execute(stmt)).all()
        return [
            ReportingSnapshotRow(portfolio=portfolio, snapshot=snapshot, instrument=instrument)
            for portfolio, snapshot, instrument in rows
        ]

    async def get_latest_fx_rate(
        self,
        *,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal | None:
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

    async def get_latest_cash_account_ids(
        self,
        *,
        portfolio_id: str,
        cash_security_ids: list[str],
        as_of_date: date,
    ) -> dict[str, str]:
        if not cash_security_ids:
            return {}

        ranked_txn_subq = (
            select(
                Transaction.settlement_cash_instrument_id.label("cash_security_id"),
                Transaction.settlement_cash_account_id.label("cash_account_id"),
                func.row_number()
                .over(
                    partition_by=Transaction.settlement_cash_instrument_id,
                    order_by=(Transaction.transaction_date.desc(), Transaction.id.desc()),
                )
                .label("rn"),
            )
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.settlement_cash_instrument_id.in_(cash_security_ids),
                Transaction.settlement_cash_account_id.is_not(None),
                Transaction.transaction_date < start_of_next_day(as_of_date),
            )
            .subquery()
        )
        stmt = select(
            ranked_txn_subq.c.cash_security_id,
            ranked_txn_subq.c.cash_account_id,
        ).where(ranked_txn_subq.c.rn == 1)
        rows = (await self.db.execute(stmt)).all()
        return {str(security_id): str(cash_account_id) for security_id, cash_account_id in rows}

    async def list_income_summary_rows(
        self,
        *,
        portfolio_ids: list[str],
        start_date: date,
        end_date: date,
        income_types: list[str],
    ) -> list[IncomeSummaryAggregateRow]:
        requested_start = start_of_day(start_date)
        ytd_start = start_of_day(date(end_date.year, 1, 1))
        end_exclusive = start_of_next_day(end_date)
        requested_window_filter = and_(
            Transaction.transaction_date >= requested_start,
            Transaction.transaction_date < end_exclusive,
        )

        absolute_gross = func.abs(Transaction.gross_transaction_amount)
        withholding_tax = func.abs(func.coalesce(Transaction.withholding_tax_amount, 0))
        other_deductions = func.abs(func.coalesce(Transaction.other_interest_deductions_amount, 0))
        direct_net_amount = case(
            (
                and_(
                    Transaction.transaction_type == "INTEREST",
                    Transaction.net_interest_amount.is_not(None),
                ),
                func.abs(Transaction.net_interest_amount),
            ),
            else_=(
                absolute_gross
                - withholding_tax
                - other_deductions
                - func.abs(func.coalesce(Transaction.trade_fee, 0))
            ),
        )

        stmt = (
            select(
                Portfolio.portfolio_id.label("portfolio_id"),
                Portfolio.booking_center_code.label("booking_center_code"),
                Portfolio.client_id.label("client_id"),
                Portfolio.base_currency.label("portfolio_currency"),
                Transaction.currency.label("source_currency"),
                Transaction.transaction_type.label("income_type"),
                func.sum(case((requested_window_filter, 1), else_=0)).label(
                    "requested_transaction_count"
                ),
                func.count(Transaction.id).label("ytd_transaction_count"),
                func.sum(case((requested_window_filter, absolute_gross), else_=0)).label(
                    "requested_gross_amount"
                ),
                func.sum(absolute_gross).label("ytd_gross_amount"),
                func.sum(case((requested_window_filter, withholding_tax), else_=0)).label(
                    "requested_withholding_tax"
                ),
                func.sum(withholding_tax).label("ytd_withholding_tax"),
                func.sum(case((requested_window_filter, other_deductions), else_=0)).label(
                    "requested_other_deductions"
                ),
                func.sum(other_deductions).label("ytd_other_deductions"),
                func.sum(case((requested_window_filter, direct_net_amount), else_=0)).label(
                    "requested_net_amount"
                ),
                func.sum(direct_net_amount).label("ytd_net_amount"),
            )
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Transaction.portfolio_id.in_(portfolio_ids),
                Transaction.transaction_date >= ytd_start,
                Transaction.transaction_date < end_exclusive,
                Transaction.transaction_type.in_(income_types),
            )
            .group_by(
                Portfolio.portfolio_id,
                Portfolio.booking_center_code,
                Portfolio.client_id,
                Portfolio.base_currency,
                Transaction.currency,
                Transaction.transaction_type,
            )
            .order_by(Portfolio.portfolio_id.asc(), Transaction.transaction_type.asc())
        )

        rows = (await self.db.execute(stmt)).mappings().all()
        return [IncomeSummaryAggregateRow(**row) for row in rows]

    async def list_activity_summary_rows(
        self,
        *,
        portfolio_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> list[ActivitySummaryAggregateRow]:
        requested_start = start_of_day(start_date)
        ytd_start = start_of_day(date(end_date.year, 1, 1))
        end_exclusive = start_of_next_day(end_date)
        requested_window_filter = and_(
            Transaction.transaction_date >= requested_start,
            Transaction.transaction_date < end_exclusive,
        )

        base_activity_amount = func.abs(
            case(
                (
                    Transaction.transaction_type == "FEE",
                    Transaction.gross_transaction_amount
                    + func.coalesce(Transaction.trade_fee, 0),
                ),
                else_=Transaction.gross_transaction_amount,
            )
        )

        bucket_expr = case(
            (Transaction.transaction_type.in_(["DEPOSIT", "TRANSFER_IN"]), literal("INFLOWS")),
            (Transaction.transaction_type.in_(["WITHDRAWAL", "TRANSFER_OUT"]), literal("OUTFLOWS")),
            (Transaction.transaction_type == "FEE", literal("FEES")),
            (Transaction.transaction_type == "TAX", literal("TAXES")),
            else_=literal(None),
        ).cast(String)

        activity_rows = (
            select(
                Portfolio.portfolio_id.label("portfolio_id"),
                Portfolio.booking_center_code.label("booking_center_code"),
                Portfolio.client_id.label("client_id"),
                Portfolio.base_currency.label("portfolio_currency"),
                Transaction.currency.label("source_currency"),
                bucket_expr.label("bucket"),
                case((requested_window_filter, 1), else_=0).label("requested_transaction_count"),
                literal(1).label("ytd_transaction_count"),
                case((requested_window_filter, base_activity_amount), else_=0).label(
                    "requested_amount"
                ),
                base_activity_amount.label("ytd_amount"),
            )
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Transaction.portfolio_id.in_(portfolio_ids),
                Transaction.transaction_date >= ytd_start,
                Transaction.transaction_date < end_exclusive,
                bucket_expr.is_not(None),
            )
        )

        withholding_tax_rows = (
            select(
                Portfolio.portfolio_id.label("portfolio_id"),
                Portfolio.booking_center_code.label("booking_center_code"),
                Portfolio.client_id.label("client_id"),
                Portfolio.base_currency.label("portfolio_currency"),
                Transaction.currency.label("source_currency"),
                literal("TAXES").label("bucket"),
                case((requested_window_filter, 1), else_=0).label("requested_transaction_count"),
                literal(1).label("ytd_transaction_count"),
                case(
                    (
                        requested_window_filter,
                        func.abs(func.coalesce(Transaction.withholding_tax_amount, 0)),
                    ),
                    else_=0,
                ).label("requested_amount"),
                func.abs(func.coalesce(Transaction.withholding_tax_amount, 0)).label("ytd_amount"),
            )
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Transaction.portfolio_id.in_(portfolio_ids),
                Transaction.transaction_date >= ytd_start,
                Transaction.transaction_date < end_exclusive,
                Transaction.withholding_tax_amount.is_not(None),
                Transaction.withholding_tax_amount != 0,
            )
        )

        activity_union = union_all(activity_rows, withholding_tax_rows).subquery()
        stmt = (
            select(
                activity_union.c.portfolio_id,
                activity_union.c.booking_center_code,
                activity_union.c.client_id,
                activity_union.c.portfolio_currency,
                activity_union.c.source_currency,
                activity_union.c.bucket,
                func.sum(activity_union.c.requested_transaction_count).label(
                    "requested_transaction_count"
                ),
                func.sum(activity_union.c.ytd_transaction_count).label("ytd_transaction_count"),
                func.sum(activity_union.c.requested_amount).label("requested_amount"),
                func.sum(activity_union.c.ytd_amount).label("ytd_amount"),
            )
            .group_by(
                activity_union.c.portfolio_id,
                activity_union.c.booking_center_code,
                activity_union.c.client_id,
                activity_union.c.portfolio_currency,
                activity_union.c.source_currency,
                activity_union.c.bucket,
            )
            .order_by(activity_union.c.portfolio_id.asc(), activity_union.c.bucket.asc())
        )

        rows = (await self.db.execute(stmt)).mappings().all()
        return [ActivitySummaryAggregateRow(**row) for row in rows]
