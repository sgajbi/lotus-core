"""SQLAlchemy persistence for position timeseries generation."""

import logging
from datetime import date
from typing import List, Optional, cast

from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    Instrument,
    PositionTimeseries,
)
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.infrastructure.persistence.timeseries_market_data_reader import (
    TimeseriesMarketDataReader,
)
from portfolio_common.infrastructure.persistence.timeseries_upsert_statements import (
    build_position_timeseries_upsert_statement,
)
from portfolio_common.utils import async_timed
from sqlalchemy import and_, func, select

logger = logging.getLogger(__name__)


class TimeseriesGenerationRepository(TimeseriesMarketDataReader):
    """Persist generated position timeseries and read their source data."""

    @async_timed(repository="TimeseriesRepository", method="get_position_timeseries")
    async def get_position_timeseries(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
    ) -> PositionTimeseries | None:
        result = await self.db.execute(
            select(PositionTimeseries).filter_by(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=a_date,
                epoch=epoch,
            )
        )
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_position_timeseries_for_dates")
    async def get_position_timeseries_for_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> dict[date, PositionTimeseries]:
        if not dates:
            return {}
        result = await self.db.execute(
            select(PositionTimeseries).where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.security_id == security_id,
                PositionTimeseries.date.in_(dates),
                PositionTimeseries.epoch == epoch,
            )
        )
        rows = cast(list[PositionTimeseries], result.scalars().all())
        return {row.date: row for row in rows}

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
            await self.db.execute(build_position_timeseries_upsert_statement(timeseries_record))
            logger.info(
                "Staged upsert for position time series for %s on %s",
                timeseries_record.security_id,
                timeseries_record.date,
            )
        except Exception as exc:
            logger.error("Failed to stage upsert for position time series: %s", exc, exc_info=True)
            raise

    @async_timed(repository="TimeseriesRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        normalized_security_id = normalize_lookup_identifier(security_id)
        result = await self.db.execute(
            select(Instrument).where(func.trim(Instrument.security_id) == normalized_security_id)
        )
        return result.scalars().first()

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
