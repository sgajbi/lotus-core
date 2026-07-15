"""SQLAlchemy persistence for position timeseries generation."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import cast

from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    PortfolioAggregationJob,
    PositionTimeseries,
)
from portfolio_common.durable_correlation import durable_correlation_diagnostics
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.infrastructure.persistence.timeseries_market_data_reader import (
    TimeseriesMarketDataReader,
)
from portfolio_common.infrastructure.persistence.timeseries_upsert_statements import (
    build_position_timeseries_upsert_statement,
)
from portfolio_common.utils import async_timed
from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..domain.position_timeseries.models import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
    PositionTimeseriesRecord,
)

logger = logging.getLogger(__name__)


class TimeseriesGenerationRepository(TimeseriesMarketDataReader):
    """Persist generated position timeseries and read their source data."""

    async def get_position_snapshot(
        self,
        snapshot_id: int,
        *,
        fallback_epoch: int,
    ) -> PositionSnapshotRecord | None:
        """Load one persisted valuation snapshot as an immutable domain record."""

        row = await self.db.get(DailyPositionSnapshot, snapshot_id)
        return (
            to_position_snapshot_record(row, fallback_epoch=fallback_epoch)
            if row is not None
            else None
        )

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
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
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
        limit: int,
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
            .limit(limit)
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

    async def stage_aggregation_jobs(
        self,
        portfolio_id: str,
        aggregation_dates: list[date],
        correlation_id: str | None,
    ) -> None:
        """Idempotently stage every materially affected portfolio day."""

        normalized_dates = sorted(set(aggregation_dates))
        if not normalized_dates:
            return

        insert_values = []
        for aggregation_date in normalized_dates:
            diagnostics = durable_correlation_diagnostics(
                correlation_id=correlation_id,
                record_family="aggregation_job",
                portfolio_id=portfolio_id,
                aggregation_date=aggregation_date,
            )
            insert_values.append(
                {
                    "portfolio_id": portfolio_id,
                    "aggregation_date": aggregation_date,
                    "status": "PENDING",
                    "correlation_id": diagnostics.correlation_id,
                    "correlation_missing_reason": diagnostics.correlation_missing_reason,
                    "alternate_lookup_key": diagnostics.alternate_lookup_key,
                }
            )

        normalized_correlation_id = insert_values[0]["correlation_id"]
        insert_statement = pg_insert(PortfolioAggregationJob).values(insert_values)
        await self.db.execute(
            insert_statement.on_conflict_do_update(
                index_elements=["portfolio_id", "aggregation_date"],
                set_={
                    "status": case(
                        (
                            PortfolioAggregationJob.status == "PROCESSING",
                            PortfolioAggregationJob.status,
                        ),
                        else_="PENDING",
                    ),
                    "correlation_id": insert_statement.excluded.correlation_id,
                    "correlation_missing_reason": (
                        insert_statement.excluded.correlation_missing_reason
                    ),
                    "alternate_lookup_key": insert_statement.excluded.alternate_lookup_key,
                    "updated_at": func.now(),
                    "failure_reason": case(
                        (
                            PortfolioAggregationJob.status == "PROCESSING",
                            "REPROCESS_REQUESTED",
                        ),
                        else_=None,
                    ),
                },
                where=or_(
                    PortfolioAggregationJob.status != "PENDING",
                    func.coalesce(PortfolioAggregationJob.correlation_id, "")
                    != (normalized_correlation_id or ""),
                ),
            )
        )
        logger.info(
            "Staged %s portfolio aggregation job(s) for %s from %s to %s.",
            len(normalized_dates),
            portfolio_id,
            normalized_dates[0],
            normalized_dates[-1],
        )


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
        source_updated_at=cast(datetime, row.updated_at),
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
        materialized_at=cast(datetime, row.updated_at),
    )
