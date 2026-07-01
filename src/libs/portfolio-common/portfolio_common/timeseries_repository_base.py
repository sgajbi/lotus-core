import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .currency_codes import normalize_currency_code
from .database_models import (
    Cashflow,
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PositionState,
    PositionTimeseries,
)
from .identifiers import normalize_lookup_identifier
from .utils import async_timed

logger = logging.getLogger(__name__)

POSITION_TIMESERIES_IDENTITY_COLUMNS = ("portfolio_id", "security_id", "date", "epoch")
PORTFOLIO_TIMESERIES_IDENTITY_COLUMNS = ("portfolio_id", "date", "epoch")
TIMESERIES_AUDIT_COLUMNS = ("created_at", "updated_at")


def _authoritative_snapshot_scope(
    job_model: type[PortfolioAggregationJob],
    snapshot_model: type[DailyPositionSnapshot],
):
    newer_snapshot = aliased(DailyPositionSnapshot)
    newer_asof_snapshot_exists = (
        select(1)
        .where(
            newer_snapshot.portfolio_id == job_model.portfolio_id,
            newer_snapshot.security_id == snapshot_model.security_id,
            newer_snapshot.date <= job_model.aggregation_date,
            or_(
                newer_snapshot.date > snapshot_model.date,
                and_(
                    newer_snapshot.date == snapshot_model.date,
                    newer_snapshot.epoch > snapshot_model.epoch,
                ),
            ),
        )
        .correlate(job_model, snapshot_model)
        .exists()
    )
    return (
        snapshot_model.portfolio_id == job_model.portfolio_id,
        snapshot_model.date <= job_model.aggregation_date,
        ~newer_asof_snapshot_exists,
    )


def _authoritative_snapshot_exists(
    job_model: type[PortfolioAggregationJob],
    snapshot_model: type[DailyPositionSnapshot],
    authoritative_snapshot_scope,
):
    return select(1).where(*authoritative_snapshot_scope).correlate(job_model).exists()


def _missing_position_timeseries_exists(
    job_model: type[PortfolioAggregationJob],
    snapshot_model: type[DailyPositionSnapshot],
    position_timeseries_model: type[PositionTimeseries],
    authoritative_snapshot_scope,
):
    matching_position_timeseries_exists = (
        select(1)
        .where(
            position_timeseries_model.portfolio_id == job_model.portfolio_id,
            position_timeseries_model.security_id == snapshot_model.security_id,
            position_timeseries_model.date == snapshot_model.date,
            position_timeseries_model.epoch == snapshot_model.epoch,
        )
        .correlate(job_model, snapshot_model)
        .exists()
    )
    return (
        select(1)
        .where(
            *authoritative_snapshot_scope,
            ~matching_position_timeseries_exists,
        )
        .correlate(job_model)
        .exists()
    )


class TimeseriesRepositoryBase:
    """Shared repository logic for timeseries worker and portfolio aggregation services."""

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
        return result.scalars().all()

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

    @async_timed(repository="TimeseriesRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioAggregationJob]:
        p1 = PortfolioAggregationJob
        dps = DailyPositionSnapshot
        position_ts = PositionTimeseries

        authoritative_snapshot_scope = _authoritative_snapshot_scope(p1, dps)
        completeness_ready_subq = _authoritative_snapshot_exists(
            p1, dps, authoritative_snapshot_scope
        ) & ~_missing_position_timeseries_exists(p1, dps, position_ts, authoritative_snapshot_scope)

        eligibility_query = (
            select(p1.id)
            .where(
                p1.status == "PENDING",
                completeness_ready_subq,
            )
            .order_by(p1.portfolio_id, p1.aggregation_date, p1.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        result_proxy = await self.db.execute(eligibility_query)
        eligible_ids = [row[0] for row in result_proxy.fetchall()]
        if not eligible_ids:
            return []

        update_query = (
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.id.in_(eligible_ids))
            .values(
                status="PROCESSING",
                updated_at=func.now(),
                attempt_count=PortfolioAggregationJob.attempt_count + 1,
            )
            .returning(PortfolioAggregationJob)
        )

        result = await self.db.execute(update_query)
        claimed_jobs = sorted(
            result.scalars().all(),
            key=lambda job: (job.portfolio_id, job.aggregation_date, job.id),
        )
        if claimed_jobs:
            logger.info("Found and claimed %s eligible aggregation jobs.", len(claimed_jobs))
        return claimed_jobs

    @async_timed(repository="TimeseriesRepository", method="recover_dispatch_failed_jobs")
    async def recover_dispatch_failed_jobs(
        self,
        job_ids: list[int],
        *,
        max_attempts: int,
        failure_reason: str,
    ) -> dict[str, int]:
        if not job_ids:
            return {"pending_count": 0, "failed_count": 0}

        failed_result = await self.db.execute(
            _dispatch_failed_aggregation_jobs_update_stmt(
                job_ids=job_ids,
                max_attempts=max_attempts,
                failure_reason=failure_reason,
            )
        )
        pending_result = await self.db.execute(
            _dispatch_retryable_aggregation_jobs_update_stmt(
                job_ids=job_ids,
                max_attempts=max_attempts,
                failure_reason=failure_reason,
            )
        )
        failed_count = int(failed_result.rowcount or 0)
        pending_count = int(pending_result.rowcount or 0)
        if failed_count or pending_count:
            logger.warning(
                "Recovered aggregation scheduler dispatch failure.",
                extra={
                    "job_ids": job_ids,
                    "pending_count": pending_count,
                    "failed_count": failed_count,
                    "max_attempts": max_attempts,
                },
            )
        return {"pending_count": pending_count, "failed_count": failed_count}

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
        return result.scalars().all()

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
        return result.scalars().all()

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
        return result.scalars().all()

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
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(
        self, timeout_minutes: int = 15, max_attempts: int = 3
    ) -> int:
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale_rows = await self._find_stale_aggregation_job_rows(stale_threshold)
        if not stale_rows:
            return 0

        failed_job_ids = _over_limit_stale_aggregation_job_ids(stale_rows, max_attempts)
        reset_job_ids = _resettable_stale_aggregation_job_ids(stale_rows, max_attempts)

        await self._mark_over_limit_stale_aggregation_jobs_failed(
            failed_job_ids,
            stale_threshold,
            max_attempts,
        )
        return await self._reset_retryable_stale_aggregation_jobs(reset_job_ids, stale_threshold)

    async def _find_stale_aggregation_job_rows(self, stale_threshold: datetime) -> list[Any]:
        return (await self.db.execute(_stale_aggregation_jobs_stmt(stale_threshold))).all()

    async def _mark_over_limit_stale_aggregation_jobs_failed(
        self,
        failed_job_ids: list[int],
        stale_threshold: datetime,
        max_attempts: int,
    ) -> None:
        if not failed_job_ids:
            return
        await self.db.execute(
            _failed_stale_aggregation_jobs_update_stmt(failed_job_ids, stale_threshold)
        )
        logger.warning(
            "Marked stale aggregation jobs as FAILED after max attempts.",
            extra={"job_ids": failed_job_ids, "max_attempts": max_attempts},
        )

    async def _reset_retryable_stale_aggregation_jobs(
        self,
        reset_job_ids: list[int],
        stale_threshold: datetime,
    ) -> int:
        if not reset_job_ids:
            return 0
        result = await self.db.execute(
            _reset_stale_aggregation_jobs_update_stmt(reset_job_ids, stale_threshold)
        )
        reset_count = result.rowcount
        if reset_count > 0:
            logger.warning(
                "Reset %s stale aggregation jobs from 'PROCESSING' to 'PENDING'.",
                reset_count,
            )
        return reset_count

    @async_timed(repository="TimeseriesRepository", method="get_job_queue_stats")
    async def get_job_queue_stats(self) -> dict:
        stmt = select(
            func.count().filter(PortfolioAggregationJob.status == "PENDING").label("pending_count"),
            func.count().filter(PortfolioAggregationJob.status == "FAILED").label("failed_count"),
            func.min(PortfolioAggregationJob.created_at)
            .filter(PortfolioAggregationJob.status == "PENDING")
            .label("oldest_pending_created_at"),
        )
        row = (await self.db.execute(stmt)).one()
        return {
            "pending_count": int(row.pending_count or 0),
            "failed_count": int(row.failed_count or 0),
            "oldest_pending_created_at": row.oldest_pending_created_at,
        }

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
        return result.scalars().all()

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


def _over_limit_stale_aggregation_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count >= max_attempts]


def _resettable_stale_aggregation_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count < max_attempts]


def _stale_aggregation_jobs_stmt(stale_threshold: datetime):
    return select(
        PortfolioAggregationJob.id,
        PortfolioAggregationJob.attempt_count,
    ).where(
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.updated_at < stale_threshold,
    )


def _failed_stale_aggregation_jobs_update_stmt(
    failed_job_ids: list[int],
    stale_threshold: datetime,
):
    return (
        _stale_aggregation_jobs_update_stmt(failed_job_ids, stale_threshold)
        .values(
            status="FAILED",
            failure_reason="Stale processing timeout exceeded max attempts",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _reset_stale_aggregation_jobs_update_stmt(
    reset_job_ids: list[int],
    stale_threshold: datetime,
):
    return _stale_aggregation_jobs_update_stmt(reset_job_ids, stale_threshold).values(
        status="PENDING",
        updated_at=func.now(),
    )


def _stale_aggregation_jobs_update_stmt(job_ids: list[int], stale_threshold: datetime):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id.in_(job_ids),
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.updated_at < stale_threshold,
    )


def _dispatch_failed_aggregation_jobs_update_stmt(
    *,
    job_ids: list[int],
    max_attempts: int,
    failure_reason: str,
):
    return (
        _dispatch_recovery_aggregation_jobs_update_stmt(job_ids)
        .where(PortfolioAggregationJob.attempt_count >= max_attempts)
        .values(status="FAILED", failure_reason=failure_reason, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


def _dispatch_retryable_aggregation_jobs_update_stmt(
    *,
    job_ids: list[int],
    max_attempts: int,
    failure_reason: str,
):
    return (
        _dispatch_recovery_aggregation_jobs_update_stmt(job_ids)
        .where(PortfolioAggregationJob.attempt_count < max_attempts)
        .values(status="PENDING", failure_reason=failure_reason, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


def _dispatch_recovery_aggregation_jobs_update_stmt(job_ids: list[int]):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id.in_(job_ids),
        PortfolioAggregationJob.status == "PROCESSING",
    )


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
