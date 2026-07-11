"""SQLAlchemy persistence shared by timeseries generation and portfolio aggregation."""

import logging
from datetime import date
from typing import Any, List, Optional, cast

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    Portfolio,
    PortfolioTimeseries,
    PositionState,
    PositionTimeseries,
)
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

POSITION_TIMESERIES_IDENTITY_COLUMNS = ("portfolio_id", "security_id", "date", "epoch")
PORTFOLIO_TIMESERIES_IDENTITY_COLUMNS = ("portfolio_id", "date", "epoch")
TIMESERIES_AUDIT_COLUMNS = ("created_at", "updated_at")


class SharedTimeseriesRepository:
    """Concrete persistence used by timeseries generation and portfolio aggregation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="TimeseriesRepository", method="get_current_epoch_for_portfolio")
    async def get_current_epoch_for_portfolio(self, portfolio_id: str) -> int:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        stmt = select(func.max(PositionState.epoch)).where(
            func.trim(PositionState.portfolio_id) == normalized_portfolio_id
        )
        result = await self.db.execute(stmt)
        max_epoch = result.scalar_one_or_none()
        return max_epoch or 0

    @async_timed(repository="TimeseriesRepository", method="get_all_snapshots_for_date")
    async def get_all_snapshots_for_date(
        self, portfolio_id: str, a_date: date
    ) -> List[DailyPositionSnapshot]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        stmt = select(DailyPositionSnapshot).where(
            func.trim(DailyPositionSnapshot.portfolio_id) == normalized_portfolio_id,
            DailyPositionSnapshot.date == a_date,
        )
        result = await self.db.execute(stmt)
        return cast(List[DailyPositionSnapshot], result.scalars().all())

    @async_timed(repository="TimeseriesRepository", method="upsert_position_timeseries")
    async def upsert_position_timeseries(self, timeseries_record: PositionTimeseries):
        try:
            await self.db.execute(_position_timeseries_upsert_stmt(timeseries_record))
            logger.info(
                "Staged upsert for position time series for %s on %s",
                timeseries_record.security_id,
                timeseries_record.date,
            )
        except Exception as exc:
            logger.error("Failed to stage upsert for position time series: %s", exc, exc_info=True)
            raise

    @async_timed(repository="TimeseriesRepository", method="upsert_portfolio_timeseries")
    async def upsert_portfolio_timeseries(self, timeseries_record: PortfolioTimeseries):
        try:
            await self.db.execute(_portfolio_timeseries_upsert_stmt(timeseries_record))
            logger.info(
                "Staged upsert for portfolio time series for %s on %s",
                timeseries_record.portfolio_id,
                timeseries_record.date,
            )
        except Exception as exc:
            logger.error("Failed to stage upsert for portfolio time series: %s", exc, exc_info=True)
            raise

    @async_timed(repository="TimeseriesRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        result = await self.db.execute(
            select(Portfolio).where(func.trim(Portfolio.portfolio_id) == normalized_portfolio_id)
        )
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        normalized_security_id = normalize_lookup_identifier(security_id)
        result = await self.db.execute(
            select(Instrument).where(func.trim(Instrument.security_id) == normalized_security_id)
        )
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_instruments_by_ids")
    async def get_instruments_by_ids(self, security_ids: List[str]) -> List[Instrument]:
        normalized_security_ids = [
            normalized
            for security_id in security_ids
            if (normalized := normalize_lookup_identifier(security_id))
        ]
        if not normalized_security_ids:
            return []
        stmt = select(Instrument).where(
            func.trim(Instrument.security_id).in_(normalized_security_ids)
        )
        result = await self.db.execute(stmt)
        return cast(List[Instrument], result.scalars().all())

    @async_timed(repository="TimeseriesRepository", method="get_fx_rate")
    async def get_fx_rate(
        self, from_currency: str, to_currency: str, a_date: date
    ) -> Optional[FxRate]:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        from_currency_expr = func.upper(func.trim(FxRate.from_currency))
        to_currency_expr = func.upper(func.trim(FxRate.to_currency))
        stmt = (
            select(FxRate)
            .filter(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date <= a_date,
            )
            .order_by(FxRate.rate_date.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_all_position_timeseries_for_date")
    async def get_all_position_timeseries_for_date(
        self, portfolio_id: str, a_date: date, epoch: int
    ) -> List[PositionTimeseries]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        position_timeseries_security_id = func.trim(PositionTimeseries.security_id)
        ranked_position_rows = (
            select(
                func.trim(PositionTimeseries.portfolio_id).label("portfolio_id"),
                position_timeseries_security_id.label("security_id"),
                PositionTimeseries.date.label("date"),
                PositionTimeseries.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=(position_timeseries_security_id,),
                    order_by=(PositionTimeseries.date.desc(), PositionTimeseries.epoch.desc()),
                )
                .label("rn"),
            )
            .where(
                func.trim(PositionTimeseries.portfolio_id) == normalized_portfolio_id,
                PositionTimeseries.date <= a_date,
                PositionTimeseries.epoch <= epoch,
            )
            .subquery()
        )

        stmt = (
            select(PositionTimeseries)
            .join(
                ranked_position_rows,
                and_(
                    func.trim(PositionTimeseries.portfolio_id)
                    == ranked_position_rows.c.portfolio_id,
                    func.trim(PositionTimeseries.security_id) == ranked_position_rows.c.security_id,
                    PositionTimeseries.date == ranked_position_rows.c.date,
                    PositionTimeseries.epoch == ranked_position_rows.c.epoch,
                ),
            )
            .where(
                ranked_position_rows.c.rn == 1,
            )
            .order_by(PositionTimeseries.security_id)
        )
        result = await self.db.execute(stmt)
        return cast(List[PositionTimeseries], result.scalars().all())

    @async_timed(repository="TimeseriesRepository", method="get_all_cashflows_for_security_date")
    async def get_all_cashflows_for_security_date(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> List[Cashflow]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        ranked_cashflows = (
            select(
                Cashflow.id.label("id"),
                func.row_number()
                .over(
                    partition_by=(Cashflow.transaction_id,),
                    order_by=(Cashflow.epoch.desc(),),
                )
                .label("rn"),
            )
            .where(
                func.trim(Cashflow.portfolio_id) == normalized_portfolio_id,
                func.trim(Cashflow.security_id) == normalized_security_id,
                Cashflow.cashflow_date == a_date,
                Cashflow.epoch <= epoch,
            )
            .subquery()
        )
        stmt = (
            select(Cashflow)
            .join(ranked_cashflows, Cashflow.id == ranked_cashflows.c.id)
            .where(ranked_cashflows.c.rn == 1)
            .order_by(Cashflow.timing.asc(), Cashflow.transaction_id.asc())
        )
        result = await self.db.execute(stmt)
        return cast(List[Cashflow], result.scalars().all())

    @async_timed(repository="TimeseriesRepository", method="get_last_portfolio_timeseries_before")
    async def get_last_portfolio_timeseries_before(
        self, portfolio_id: str, a_date: date
    ) -> Optional[PortfolioTimeseries]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        stmt = (
            select(PortfolioTimeseries)
            .filter(
                func.trim(PortfolioTimeseries.portfolio_id) == normalized_portfolio_id,
                PortfolioTimeseries.date < a_date,
            )
            .order_by(PortfolioTimeseries.date.desc(), PortfolioTimeseries.epoch.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_latest_snapshots_for_date")
    async def get_latest_snapshots_for_date(
        self, portfolio_id: str, a_date: date
    ) -> List[DailyPositionSnapshot]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        snapshot_security_id = func.trim(DailyPositionSnapshot.security_id)
        latest_snapshot_epochs = (
            select(
                snapshot_security_id.label("security_id"),
                DailyPositionSnapshot.date.label("date"),
                func.max(DailyPositionSnapshot.epoch).label("epoch"),
            )
            .where(
                func.trim(DailyPositionSnapshot.portfolio_id) == normalized_portfolio_id,
                DailyPositionSnapshot.date <= a_date,
            )
            .group_by(snapshot_security_id, DailyPositionSnapshot.date)
            .subquery()
        )

        ranked_snapshots = select(
            latest_snapshot_epochs.c.security_id,
            latest_snapshot_epochs.c.date,
            latest_snapshot_epochs.c.epoch,
            func.row_number()
            .over(
                partition_by=latest_snapshot_epochs.c.security_id,
                order_by=(
                    latest_snapshot_epochs.c.date.desc(),
                    latest_snapshot_epochs.c.epoch.desc(),
                ),
            )
            .label("rn"),
        ).subquery()

        stmt = (
            select(DailyPositionSnapshot)
            .join(
                ranked_snapshots,
                and_(
                    func.trim(DailyPositionSnapshot.security_id) == ranked_snapshots.c.security_id,
                    DailyPositionSnapshot.date == ranked_snapshots.c.date,
                    DailyPositionSnapshot.epoch == ranked_snapshots.c.epoch,
                ),
            )
            .where(
                func.trim(DailyPositionSnapshot.portfolio_id) == normalized_portfolio_id,
                ranked_snapshots.c.rn == 1,
            )
            .order_by(DailyPositionSnapshot.security_id)
        )
        result = await self.db.execute(stmt)
        return cast(List[DailyPositionSnapshot], result.scalars().all())

    @async_timed(repository="TimeseriesRepository", method="get_last_snapshot_before")
    async def get_last_snapshot_before(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> Optional[DailyPositionSnapshot]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(DailyPositionSnapshot)
            .filter(
                func.trim(DailyPositionSnapshot.portfolio_id) == normalized_portfolio_id,
                func.trim(DailyPositionSnapshot.security_id) == normalized_security_id,
                DailyPositionSnapshot.date < a_date,
                DailyPositionSnapshot.epoch <= epoch,
            )
            .order_by(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.epoch.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_next_snapshots_after")
    async def get_next_snapshots_after(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
        max_rows: int,
    ) -> List[DailyPositionSnapshot]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        ranked_future_snapshots = (
            select(
                DailyPositionSnapshot.id.label("id"),
                func.row_number()
                .over(
                    partition_by=(DailyPositionSnapshot.date,),
                    order_by=(DailyPositionSnapshot.epoch.desc(),),
                )
                .label("rn"),
            )
            .where(
                func.trim(DailyPositionSnapshot.portfolio_id) == normalized_portfolio_id,
                func.trim(DailyPositionSnapshot.security_id) == normalized_security_id,
                DailyPositionSnapshot.date > a_date,
                DailyPositionSnapshot.epoch <= epoch,
            )
            .subquery()
        )
        stmt = (
            select(DailyPositionSnapshot)
            .join(ranked_future_snapshots, DailyPositionSnapshot.id == ranked_future_snapshots.c.id)
            .where(ranked_future_snapshots.c.rn == 1)
            .order_by(DailyPositionSnapshot.date.asc())
            .limit(max_rows)
        )
        result = await self.db.execute(stmt)
        return cast(List[DailyPositionSnapshot], result.scalars().all())

    @async_timed(repository="TimeseriesRepository", method="get_cashflows_for_security_dates")
    async def get_cashflows_for_security_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: List[date],
        epoch: int,
    ) -> dict[date, List[Cashflow]]:
        if not dates:
            return {}
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        ranked_cashflows = (
            select(
                Cashflow.id.label("id"),
                Cashflow.cashflow_date.label("cashflow_date"),
                func.row_number()
                .over(
                    partition_by=(Cashflow.transaction_id,),
                    order_by=(Cashflow.epoch.desc(),),
                )
                .label("rn"),
            )
            .where(
                func.trim(Cashflow.portfolio_id) == normalized_portfolio_id,
                func.trim(Cashflow.security_id) == normalized_security_id,
                Cashflow.cashflow_date.in_(dates),
                Cashflow.epoch <= epoch,
            )
            .subquery()
        )
        stmt = (
            select(Cashflow)
            .join(ranked_cashflows, Cashflow.id == ranked_cashflows.c.id)
            .where(ranked_cashflows.c.rn == 1)
            .order_by(
                Cashflow.cashflow_date.asc(),
                Cashflow.timing.asc(),
                Cashflow.transaction_id.asc(),
            )
        )
        result = await self.db.execute(stmt)
        grouped: dict[date, List[Cashflow]] = {cashflow_date: [] for cashflow_date in dates}
        for cashflow in result.scalars().all():
            grouped.setdefault(cashflow.cashflow_date, []).append(cashflow)
        return grouped


def _position_timeseries_upsert_stmt(timeseries_record: PositionTimeseries):
    return _timeseries_upsert_stmt(
        PositionTimeseries,
        timeseries_record,
        POSITION_TIMESERIES_IDENTITY_COLUMNS,
    )


def _portfolio_timeseries_upsert_stmt(timeseries_record: PortfolioTimeseries):
    return _timeseries_upsert_stmt(
        PortfolioTimeseries,
        timeseries_record,
        PORTFOLIO_TIMESERIES_IDENTITY_COLUMNS,
    )


def _timeseries_upsert_stmt(model: Any, timeseries_record: Any, identity_columns: tuple[str, ...]):
    insert_values = _timeseries_insert_values(timeseries_record)
    return (
        pg_insert(model)
        .values(**insert_values)
        .on_conflict_do_update(
            index_elements=list(identity_columns),
            set_=_timeseries_update_values(insert_values, identity_columns),
        )
    )


def _timeseries_insert_values(timeseries_record: Any) -> dict[str, Any]:
    return {
        column.name: getattr(timeseries_record, column.name)
        for column in timeseries_record.__table__.columns
        if column.name not in TIMESERIES_AUDIT_COLUMNS
    }


def _timeseries_update_values(
    insert_values: dict[str, Any],
    identity_columns: tuple[str, ...],
) -> dict[str, Any]:
    update_values = {
        name: value for name, value in insert_values.items() if name not in identity_columns
    }
    update_values["updated_at"] = func.now()
    return update_values
