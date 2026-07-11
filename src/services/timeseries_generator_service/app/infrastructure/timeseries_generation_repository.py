"""SQLAlchemy persistence for position timeseries generation."""

import logging
from datetime import date
from decimal import Decimal
from typing import cast

from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
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
from sqlalchemy import func, select

from ..domain.timeseries_records import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
    PositionTimeseriesRecord,
)

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
    ) -> PositionTimeseriesRecord | None:
        result = await self.db.execute(
            select(PositionTimeseries).filter_by(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=a_date,
                epoch=epoch,
            )
        )
        row = result.scalars().first()
        return _position_timeseries_record(row) if row is not None else None

    @async_timed(repository="TimeseriesRepository", method="get_position_timeseries_for_dates")
    async def get_position_timeseries_for_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> dict[date, PositionTimeseriesRecord]:
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
        records = (_position_timeseries_record(row) for row in rows)
        return {record.date: record for record in records}

    @async_timed(repository="TimeseriesRepository", method="upsert_position_timeseries")
    async def upsert_position_timeseries(self, timeseries_record: PositionTimeseriesRecord) -> None:
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

    @async_timed(repository="TimeseriesRepository", method="get_all_cashflows_for_security_date")
    async def get_all_cashflows_for_security_date(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> list[PositionCashflowRecord]:
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
        rows = cast(list[Cashflow], result.scalars().all())
        return [_position_cashflow_record(row) for row in rows]

    @async_timed(repository="TimeseriesRepository", method="get_last_snapshot_before")
    async def get_last_snapshot_before(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> PositionSnapshotRecord | None:
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
        row = result.scalars().first()
        return to_position_snapshot_record(row) if row is not None else None

    @async_timed(repository="TimeseriesRepository", method="get_next_snapshots_after")
    async def get_next_snapshots_after(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
        max_rows: int,
    ) -> list[PositionSnapshotRecord]:
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
        rows = cast(list[DailyPositionSnapshot], result.scalars().all())
        return [to_position_snapshot_record(row) for row in rows]

    @async_timed(repository="TimeseriesRepository", method="get_cashflows_for_security_dates")
    async def get_cashflows_for_security_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> dict[date, list[PositionCashflowRecord]]:
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
        grouped: dict[date, list[PositionCashflowRecord]] = {
            cashflow_date: [] for cashflow_date in dates
        }
        for row in cast(list[Cashflow], result.scalars().all()):
            cashflow = _position_cashflow_record(row)
            grouped.setdefault(cashflow.cashflow_date, []).append(cashflow)
        return grouped


def to_position_snapshot_record(
    row: DailyPositionSnapshot,
    *,
    fallback_epoch: int = 0,
) -> PositionSnapshotRecord:
    """Detach valued fields used by timeseries calculation from an ORM snapshot."""

    return PositionSnapshotRecord(
        portfolio_id=str(row.portfolio_id),
        security_id=str(row.security_id),
        date=cast(date, row.date),
        epoch=int(row.epoch if row.epoch is not None else fallback_epoch),
        quantity=cast(Decimal, row.quantity),
        cost_basis_local=cast(Decimal | None, row.cost_basis_local),
        market_value_local=cast(Decimal | None, row.market_value_local),
    )


def _position_cashflow_record(row: Cashflow) -> PositionCashflowRecord:
    return PositionCashflowRecord(
        transaction_id=str(row.transaction_id),
        cashflow_date=cast(date, row.cashflow_date),
        epoch=int(row.epoch),
        amount=cast(Decimal, row.amount),
        classification=str(row.classification),
        timing=str(row.timing),
        is_position_flow=bool(row.is_position_flow),
        is_portfolio_flow=bool(row.is_portfolio_flow),
    )


def _position_timeseries_record(row: PositionTimeseries) -> PositionTimeseriesRecord:
    return PositionTimeseriesRecord(
        portfolio_id=str(row.portfolio_id),
        security_id=str(row.security_id),
        date=cast(date, row.date),
        epoch=int(row.epoch),
        bod_market_value=cast(Decimal, row.bod_market_value),
        bod_cashflow_position=cast(Decimal, row.bod_cashflow_position),
        eod_cashflow_position=cast(Decimal, row.eod_cashflow_position),
        bod_cashflow_portfolio=cast(Decimal, row.bod_cashflow_portfolio),
        eod_cashflow_portfolio=cast(Decimal, row.eod_cashflow_portfolio),
        eod_market_value=cast(Decimal, row.eod_market_value),
        fees=cast(Decimal, row.fees),
        quantity=cast(Decimal, row.quantity),
        cost=cast(Decimal, row.cost),
    )
