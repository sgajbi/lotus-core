from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    CashAccountMaster,
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    InstrumentLookthroughComponent,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .currency_codes import currency_code_sql_expr, normalize_currency_code
from .date_filters import start_of_next_day
from .identifier_normalization import normalize_security_id


@dataclass(frozen=True)
class ReportingSnapshotRow:
    portfolio: Portfolio
    snapshot: DailyPositionSnapshot
    instrument: Instrument | None


@dataclass(frozen=True)
class InstrumentLookthroughComponentRow:
    parent_security_id: str
    component_security_id: str
    component_weight: Decimal
    component_instrument: Instrument | None


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
        instrument_asset_class: str | None = None,
    ) -> list[ReportingSnapshotRow]:
        history_security_id = func.trim(PositionHistory.security_id)
        state_security_id = func.trim(PositionState.security_id)
        snapshot_security_id = func.trim(DailyPositionSnapshot.security_id)
        instrument_security_id = func.trim(Instrument.security_id)
        latest_history_stmt = select(
            PositionHistory.portfolio_id.label("portfolio_id"),
            history_security_id.label("security_id"),
            PositionHistory.epoch.label("epoch"),
            PositionHistory.quantity.label("quantity"),
            func.row_number()
            .over(
                partition_by=(
                    PositionHistory.portfolio_id,
                    history_security_id,
                ),
                order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
            )
            .label("rn"),
        ).join(
            PositionState,
            and_(
                PositionHistory.portfolio_id == PositionState.portfolio_id,
                history_security_id == state_security_id,
                PositionHistory.epoch == PositionState.epoch,
            ),
        )
        normalized_asset_class = str(instrument_asset_class or "").strip().upper()
        if normalized_asset_class:
            eligible_instrument_ids = (
                select(instrument_security_id.label("security_id"))
                .where(
                    instrument_security_id != "",
                    func.upper(func.trim(Instrument.asset_class)) == normalized_asset_class,
                )
                .subquery()
            )
            latest_history_stmt = latest_history_stmt.join(
                eligible_instrument_ids,
                history_security_id == eligible_instrument_ids.c.security_id,
            )
        latest_history_subq = latest_history_stmt.where(
            PositionHistory.portfolio_id.in_(portfolio_ids),
            PositionHistory.position_date <= as_of_date,
        ).subquery()
        latest_open_history_subq = (
            select(latest_history_subq)
            .where(
                latest_history_subq.c.rn == 1,
                latest_history_subq.c.quantity != 0,
            )
            .subquery()
        )
        ranked_snapshot_subq = (
            select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=(
                        DailyPositionSnapshot.portfolio_id,
                        snapshot_security_id,
                    ),
                    order_by=(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            )
            .join(
                latest_open_history_subq,
                and_(
                    DailyPositionSnapshot.portfolio_id == latest_open_history_subq.c.portfolio_id,
                    snapshot_security_id == latest_open_history_subq.c.security_id,
                    DailyPositionSnapshot.epoch == latest_open_history_subq.c.epoch,
                    DailyPositionSnapshot.quantity == latest_open_history_subq.c.quantity,
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
            .outerjoin(Instrument, instrument_security_id == snapshot_security_id)
            .order_by(
                DailyPositionSnapshot.portfolio_id.asc(),
                snapshot_security_id.asc(),
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

        normalized_cash_security_ids = [
            security_id
            for value in cash_security_ids
            if (security_id := normalize_security_id(value))
        ]
        if not normalized_cash_security_ids:
            return {}

        cash_security_id = func.trim(Transaction.settlement_cash_instrument_id)
        ranked_txn_subq = (
            select(
                cash_security_id.label("cash_security_id"),
                Transaction.settlement_cash_account_id.label("cash_account_id"),
                func.row_number()
                .over(
                    partition_by=cash_security_id,
                    order_by=(Transaction.transaction_date.desc(), Transaction.id.desc()),
                )
                .label("rn"),
            )
            .where(
                Transaction.portfolio_id == portfolio_id,
                cash_security_id.in_(normalized_cash_security_ids),
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
        return {
            normalize_security_id(security_id): str(cash_account_id)
            for security_id, cash_account_id in rows
            if normalize_security_id(security_id)
        }

    async def list_cash_account_masters(
        self,
        *,
        portfolio_id: str,
        as_of_date: date | None,
    ) -> list[CashAccountMaster]:
        stmt = select(CashAccountMaster).where(CashAccountMaster.portfolio_id == portfolio_id)
        if as_of_date is not None:
            stmt = stmt.where(
                or_(
                    CashAccountMaster.opened_on.is_(None),
                    CashAccountMaster.opened_on <= as_of_date,
                ),
                or_(
                    CashAccountMaster.closed_on.is_(None),
                    CashAccountMaster.closed_on >= as_of_date,
                ),
            )
        stmt = stmt.order_by(
            CashAccountMaster.account_currency.asc(),
            CashAccountMaster.cash_account_id.asc(),
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_instrument_lookthrough_components(
        self,
        *,
        parent_security_ids: list[str],
        as_of_date: date,
    ) -> list[InstrumentLookthroughComponentRow]:
        normalized_parent_security_ids = [
            security_id
            for value in parent_security_ids
            if (security_id := normalize_security_id(value))
        ]
        normalized_parent_security_ids = list(dict.fromkeys(normalized_parent_security_ids))
        if not normalized_parent_security_ids:
            return []

        parent_security_id = func.trim(InstrumentLookthroughComponent.parent_security_id)
        component_security_id = func.trim(InstrumentLookthroughComponent.component_security_id)
        instrument_security_id = func.trim(Instrument.security_id)
        stmt = (
            select(
                parent_security_id.label("parent_security_id"),
                component_security_id.label("component_security_id"),
                InstrumentLookthroughComponent.component_weight,
                Instrument,
            )
            .outerjoin(
                Instrument,
                instrument_security_id == component_security_id,
            )
            .where(
                parent_security_id.in_(normalized_parent_security_ids),
                component_security_id != "",
                InstrumentLookthroughComponent.effective_from <= as_of_date,
                or_(
                    InstrumentLookthroughComponent.effective_to.is_(None),
                    InstrumentLookthroughComponent.effective_to >= as_of_date,
                ),
            )
            .order_by(
                parent_security_id.asc(),
                component_security_id.asc(),
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            InstrumentLookthroughComponentRow(
                parent_security_id=normalize_security_id(parent_security_id),
                component_security_id=normalize_security_id(component_security_id),
                component_weight=component_weight,
                component_instrument=component_instrument,
            )
            for (
                parent_security_id,
                component_security_id,
                component_weight,
                component_instrument,
            ) in rows
        ]
