"""SQLAlchemy persistence for portfolio aggregation data and job queues."""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Portfolio,
    PortfolioAggregationJob,
    PositionTimeseries,
)
from portfolio_common.domain.calculation_lineage import calculation_lineage_from_payload
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.infrastructure.persistence.statement_batching import (
    StatementBatchOperation,
    iter_statement_chunks,
    observe_multi_statement_batch,
)
from portfolio_common.infrastructure.persistence.timeseries_market_data_reader import (
    TimeseriesMarketDataReader,
)
from portfolio_common.infrastructure.persistence.timeseries_upsert_statements import (
    build_portfolio_timeseries_upsert_statement,
)
from portfolio_common.utils import async_timed
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.orm import aliased

from ..domain.aggregation_jobs.models import (
    AggregationJobCompletionDisposition,
    AggregationJobFailureDisposition,
    AggregationJobLease,
    AggregationJobLeaseClaim,
    ClaimedAggregationJob,
    ExpiredAggregationJobRecovery,
)
from ..domain.portfolio_timeseries.models import (
    PortfolioAggregationScope,
    PortfolioTimeseriesRecord,
)
from ..domain.position_timeseries.models import PositionTimeseriesRecord

logger = logging.getLogger(__name__)

AGGREGATION_REPROCESS_REQUESTED = "REPROCESS_REQUESTED"
AGGREGATION_STALE_RECOVERY_COHORT_LIMIT = 1_000


@dataclass(frozen=True)
class _EligibleAggregationJobTarget:
    job_id: int
    target_epoch: int
    source_advanced: bool


class PortfolioAggregationRepository(TimeseriesMarketDataReader):
    """Persist portfolio aggregation outputs and coordinate aggregation jobs."""

    @async_timed(repository="TimeseriesRepository", method="upsert_portfolio_timeseries")
    async def upsert_portfolio_timeseries(self, record: PortfolioTimeseriesRecord) -> None:
        try:
            await self.db.execute(build_portfolio_timeseries_upsert_statement(record))
            logger.debug(
                "Staged portfolio time-series upsert.",
                extra={
                    "portfolio_id": record.portfolio_id,
                    "aggregation_date": record.date.isoformat(),
                },
            )
        except Exception as exc:
            logger.error("Failed to stage portfolio time series upsert: %s", exc, exc_info=True)
            raise

    async def complete_or_requeue_job(
        self,
        *,
        job_id: int,
        lease_token: str,
        target_epoch: int,
        source_revision: int,
    ) -> AggregationJobCompletionDisposition:
        """Release one job only when its durable lease token still matches."""

        if await self._requeue_superseded_claim(
            job_id=job_id,
            lease_token=lease_token,
            target_epoch=target_epoch,
            source_revision=source_revision,
        ):
            return AggregationJobCompletionDisposition.REQUEUED

        complete_result = await self.db.execute(
            _owned_claim_update(job_id=job_id, lease_token=lease_token)
            .where(
                PortfolioAggregationJob.target_epoch == target_epoch,
                PortfolioAggregationJob.source_revision == source_revision,
                ~_unmaterialized_authoritative_snapshot_exists(target_epoch),
            )
            .values(
                status="COMPLETE",
                failure_reason=None,
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
        )
        if int(complete_result.rowcount or 0) == 1:
            return AggregationJobCompletionDisposition.COMPLETE
        if await self._requeue_superseded_claim(
            job_id=job_id,
            lease_token=lease_token,
            target_epoch=target_epoch,
            source_revision=source_revision,
        ):
            return AggregationJobCompletionDisposition.REQUEUED
        return AggregationJobCompletionDisposition.LOST_OWNERSHIP

    async def fail_or_requeue_job(
        self,
        *,
        job_id: int,
        lease_token: str,
        target_epoch: int,
        source_revision: int,
    ) -> AggregationJobFailureDisposition:
        """Fail current work or requeue it when newer source identity superseded the claim."""

        if await self._requeue_superseded_claim(
            job_id=job_id,
            lease_token=lease_token,
            target_epoch=target_epoch,
            source_revision=source_revision,
        ):
            return AggregationJobFailureDisposition.REQUEUED

        result = await self.db.execute(
            _owned_claim_update(job_id=job_id, lease_token=lease_token)
            .where(
                PortfolioAggregationJob.target_epoch == target_epoch,
                PortfolioAggregationJob.source_revision == source_revision,
                ~_unmaterialized_authoritative_snapshot_exists(target_epoch),
            )
            .values(
                status="FAILED",
                failure_reason=None,
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
        )
        if int(result.rowcount or 0) == 1:
            return AggregationJobFailureDisposition.FAILED
        if await self._requeue_superseded_claim(
            job_id=job_id,
            lease_token=lease_token,
            target_epoch=target_epoch,
            source_revision=source_revision,
        ):
            return AggregationJobFailureDisposition.REQUEUED
        return AggregationJobFailureDisposition.LOST_OWNERSHIP

    async def _requeue_superseded_claim(
        self,
        *,
        job_id: int,
        lease_token: str,
        target_epoch: int,
        source_revision: int,
    ) -> bool:
        result = await self.db.execute(
            _owned_claim_update(job_id=job_id, lease_token=lease_token)
            .where(
                or_(
                    PortfolioAggregationJob.target_epoch != target_epoch,
                    PortfolioAggregationJob.source_revision != source_revision,
                    PortfolioAggregationJob.failure_reason == AGGREGATION_REPROCESS_REQUESTED,
                    _unmaterialized_authoritative_snapshot_exists(target_epoch),
                )
            )
            .values(
                status="PENDING",
                failure_reason=None,
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
        )
        return int(result.rowcount or 0) == 1

    @async_timed(repository="TimeseriesRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> PortfolioAggregationScope | None:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        result = await self.db.execute(
            select(Portfolio).where(func.trim(Portfolio.portfolio_id) == normalized_portfolio_id)
        )
        row = result.scalars().first()
        return _portfolio_aggregation_scope(row) if row is not None else None

    @async_timed(repository="TimeseriesRepository", method="get_all_position_timeseries_for_date")
    async def get_all_position_timeseries_for_date(
        self,
        portfolio_id: str,
        a_date: date,
        epoch: int,
    ) -> list[PositionTimeseriesRecord]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        security_id = func.trim(PositionTimeseries.security_id)
        ranked_rows = (
            select(
                func.trim(PositionTimeseries.portfolio_id).label("portfolio_id"),
                security_id.label("security_id"),
                PositionTimeseries.date.label("date"),
                PositionTimeseries.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=(security_id,),
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
        result = await self.db.execute(
            select(PositionTimeseries)
            .join(
                ranked_rows,
                and_(
                    func.trim(PositionTimeseries.portfolio_id) == ranked_rows.c.portfolio_id,
                    func.trim(PositionTimeseries.security_id) == ranked_rows.c.security_id,
                    PositionTimeseries.date == ranked_rows.c.date,
                    PositionTimeseries.epoch == ranked_rows.c.epoch,
                ),
            )
            .where(ranked_rows.c.rn == 1)
            .order_by(PositionTimeseries.security_id)
        )
        rows = cast(list[PositionTimeseries], result.scalars().all())
        return [_position_timeseries_record(row) for row in rows]

    async def _find_eligible_job_targets(
        self,
        batch_size: int,
    ) -> list[_EligibleAggregationJobTarget]:
        job = PortfolioAggregationJob
        snapshot = DailyPositionSnapshot
        position_timeseries = PositionTimeseries
        authoritative_scope = _authoritative_snapshot_scope(job, snapshot)
        authoritative_target_epoch = _authoritative_target_epoch(
            job,
            snapshot,
            authoritative_scope,
        )
        source_advanced = authoritative_target_epoch > job.target_epoch
        completeness_ready = (
            _authoritative_snapshot_exists(job, snapshot, authoritative_scope)
            & ~_missing_position_timeseries_exists(
                job,
                snapshot,
                position_timeseries,
                authoritative_scope,
            )
            & ~_unmaterialized_authoritative_snapshot_exists(authoritative_target_epoch)
        )
        result_proxy = await self.db.execute(
            select(job.id, authoritative_target_epoch, source_advanced)
            .where(job.status == "PENDING", completeness_ready)
            .order_by(job.portfolio_id, job.aggregation_date, job.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        return [
            _EligibleAggregationJobTarget(
                job_id=int(row[0]),
                target_epoch=int(row[1]),
                source_advanced=bool(row[2]),
            )
            for row in result_proxy.fetchall()
        ]

    async def _claim_eligible_job_rows(
        self,
        eligible_targets: list[_EligibleAggregationJobTarget],
        *,
        lease: AggregationJobLeaseClaim,
    ) -> list[PortfolioAggregationJob]:
        if not eligible_targets:
            return []
        job = PortfolioAggregationJob
        target_epoch_by_job = {target.job_id: target.target_epoch for target in eligible_targets}
        source_advanced_by_job = {
            target.job_id: target.source_advanced for target in eligible_targets
        }
        selected_target_epoch = case(
            target_epoch_by_job,
            value=job.id,
            else_=job.target_epoch,
        )
        selected_source_advanced = case(
            source_advanced_by_job,
            value=job.id,
            else_=False,
        )
        promoted_target_epoch = func.greatest(
            job.target_epoch,
            selected_target_epoch,
        )
        result = await self.db.execute(
            update(job)
            .where(job.id.in_(target_epoch_by_job))
            .values(
                status="PROCESSING",
                updated_at=func.now(),
                attempt_count=job.attempt_count + 1,
                target_epoch=promoted_target_epoch,
                source_revision=case(
                    (selected_source_advanced, job.source_revision + 1),
                    else_=job.source_revision,
                ),
                lease_owner=lease.owner,
                lease_token=lease.token,
                lease_expires_at=func.clock_timestamp()
                + func.make_interval(0, 0, 0, 0, 0, 0, lease.duration_seconds),
            )
            .returning(job)
            .execution_options(populate_existing=True)
        )
        return sorted(
            cast(list[PortfolioAggregationJob], result.scalars().all()),
            key=lambda claimed: (
                claimed.portfolio_id,
                claimed.aggregation_date,
                claimed.id,
            ),
        )

    @async_timed(repository="TimeseriesRepository", method="claim_eligible_jobs")
    async def claim_eligible_jobs(
        self,
        *,
        batch_size: int,
        lease: AggregationJobLeaseClaim,
    ) -> list[ClaimedAggregationJob]:
        """Claim one ready batch with durable, fenced lease ownership."""

        eligible_targets = await self._find_eligible_job_targets(batch_size)
        claimed_rows = await self._claim_eligible_job_rows(eligible_targets, lease=lease)
        if claimed_rows:
            logger.info("Found and leased %s eligible aggregation jobs.", len(claimed_rows))
        return [_claimed_aggregation_job(row) for row in claimed_rows]

    @async_timed(repository="TimeseriesRepository", method="recover_expired_job_leases")
    async def recover_expired_job_leases(
        self,
        *,
        max_attempts: int,
    ) -> ExpiredAggregationJobRecovery:
        """Requeue or fail expired claims while rechecking expiry on every write."""

        expired_rows = cast(
            list[Any],
            (await self.db.execute(_expired_job_leases_statement())).all(),
        )
        failed_job_ids = [
            row.id
            for row in expired_rows
            if row.attempt_count >= max_attempts
            and row.failure_reason != AGGREGATION_REPROCESS_REQUESTED
        ]
        failed_job_id_set = set(failed_job_ids)
        requeue_job_ids = sorted(row.id for row in expired_rows if row.id not in failed_job_id_set)
        failed_count = await self._fail_expired_job_leases(failed_job_ids)
        requeued_count = await self._requeue_expired_job_leases(requeue_job_ids)
        return ExpiredAggregationJobRecovery(
            requeued_count=requeued_count,
            failed_count=failed_count,
        )

    async def _fail_expired_job_leases(self, job_ids: list[int]) -> int:
        normalized_ids = sorted(set(job_ids))
        if not normalized_ids:
            return 0
        observe_multi_statement_batch(
            operation=StatementBatchOperation.AGGREGATION_STALE_FAILED_UPDATE,
            item_count=len(normalized_ids),
            binds_per_row=1,
            reserved_binds=9,
        )
        failed_count = 0
        for chunk in iter_statement_chunks(
            normalized_ids,
            binds_per_row=1,
            reserved_binds=9,
        ):
            result = await self.db.execute(
                _expired_job_leases_update(list(chunk))
                .where(
                    func.coalesce(PortfolioAggregationJob.failure_reason, "")
                    != AGGREGATION_REPROCESS_REQUESTED
                )
                .values(
                    status="FAILED",
                    failure_reason="Aggregation job lease expired after max attempts",
                    updated_at=func.now(),
                    **_cleared_lease_values(),
                )
                .execution_options(synchronize_session=False)
            )
            failed_count += int(result.rowcount or 0)
        return failed_count

    async def _requeue_expired_job_leases(self, job_ids: list[int]) -> int:
        normalized_ids = sorted(set(job_ids))
        if not normalized_ids:
            return 0
        observe_multi_statement_batch(
            operation=StatementBatchOperation.AGGREGATION_STALE_REQUEUE_UPDATE,
            item_count=len(normalized_ids),
            binds_per_row=1,
            reserved_binds=7,
        )
        requeued_count = 0
        for chunk in iter_statement_chunks(
            normalized_ids,
            binds_per_row=1,
            reserved_binds=7,
        ):
            result = await self.db.execute(
                _expired_job_leases_update(list(chunk))
                .values(
                    status="PENDING",
                    failure_reason=None,
                    updated_at=func.now(),
                    **_cleared_lease_values(),
                )
                .execution_options(synchronize_session=False)
            )
            requeued_count += int(result.rowcount or 0)
        return requeued_count

    @async_timed(repository="TimeseriesRepository", method="get_job_queue_stats")
    async def get_job_queue_stats(self) -> dict[str, Any]:
        row = (
            await self.db.execute(
                select(
                    func.count()
                    .filter(PortfolioAggregationJob.status == "PENDING")
                    .label("pending_count"),
                    func.count()
                    .filter(PortfolioAggregationJob.status == "FAILED")
                    .label("failed_count"),
                    func.min(PortfolioAggregationJob.created_at)
                    .filter(PortfolioAggregationJob.status == "PENDING")
                    .label("oldest_pending_created_at"),
                ).where(PortfolioAggregationJob.status.in_(("PENDING", "FAILED")))
            )
        ).one()
        return {
            "pending_count": int(row.pending_count or 0),
            "failed_count": int(row.failed_count or 0),
            "oldest_pending_created_at": row.oldest_pending_created_at,
        }


def _portfolio_aggregation_scope(row: Portfolio) -> PortfolioAggregationScope:
    return PortfolioAggregationScope(
        portfolio_id=str(row.portfolio_id),
        base_currency=str(row.base_currency),
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
        calculation_lineage=calculation_lineage_from_payload(row.calculation_lineage),
    )


def _claimed_aggregation_job(row: PortfolioAggregationJob) -> ClaimedAggregationJob:
    lease_expires_at = cast(datetime | None, row.lease_expires_at)
    if row.lease_owner is None or row.lease_token is None or lease_expires_at is None:
        raise ValueError("Claimed aggregation job is missing durable lease identity.")
    return ClaimedAggregationJob(
        id=int(row.id),
        portfolio_id=str(row.portfolio_id),
        aggregation_date=cast(date, row.aggregation_date),
        aggregation_revision=int(row.attempt_count),
        target_epoch=int(row.target_epoch),
        source_revision=int(row.source_revision),
        correlation_id=str(row.correlation_id) if row.correlation_id is not None else None,
        lease=AggregationJobLease(
            owner=str(row.lease_owner),
            token=str(row.lease_token),
            expires_at=lease_expires_at,
        ),
    )


def _authoritative_snapshot_scope(job_model, snapshot_model):
    newer_snapshot = aliased(DailyPositionSnapshot)
    newer_snapshot_exists = (
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
        ~newer_snapshot_exists,
    )


def _authoritative_target_epoch(job_model, snapshot_model, authoritative_scope):
    """Return the latest fully scoped source epoch that one portfolio day must aggregate."""

    return (
        select(func.max(snapshot_model.epoch))
        .where(*authoritative_scope)
        .correlate(job_model)
        .scalar_subquery()
    )


def _authoritative_snapshot_exists(job_model, snapshot_model, authoritative_scope):
    return select(1).where(*authoritative_scope).correlate(job_model).exists()


def _missing_position_timeseries_exists(
    job_model,
    snapshot_model,
    position_timeseries_model,
    authoritative_scope,
):
    matching_timeseries_exists = (
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
        .where(*authoritative_scope, ~matching_timeseries_exists)
        .correlate(job_model)
        .exists()
    )


def _expired_job_leases_statement():
    return (
        select(
            PortfolioAggregationJob.id,
            PortfolioAggregationJob.attempt_count,
            PortfolioAggregationJob.failure_reason,
        )
        .where(
            PortfolioAggregationJob.status == "PROCESSING",
            PortfolioAggregationJob.lease_expires_at <= func.clock_timestamp(),
        )
        .order_by(
            PortfolioAggregationJob.lease_expires_at.asc(),
            PortfolioAggregationJob.id.asc(),
        )
        .limit(AGGREGATION_STALE_RECOVERY_COHORT_LIMIT)
        .with_for_update(skip_locked=True)
    )


def _unmaterialized_authoritative_snapshot_exists(target_epoch: int):
    snapshot = aliased(DailyPositionSnapshot)
    newer_snapshot = aliased(DailyPositionSnapshot)
    position_timeseries = aliased(PositionTimeseries)
    newer_snapshot_exists = (
        select(1)
        .where(
            newer_snapshot.portfolio_id == PortfolioAggregationJob.portfolio_id,
            newer_snapshot.security_id == snapshot.security_id,
            newer_snapshot.date <= PortfolioAggregationJob.aggregation_date,
            or_(
                newer_snapshot.date > snapshot.date,
                and_(
                    newer_snapshot.date == snapshot.date,
                    newer_snapshot.epoch > snapshot.epoch,
                ),
            ),
        )
        .correlate(PortfolioAggregationJob, snapshot)
        .exists()
    )
    materialized_snapshot_exists = (
        select(1)
        .where(
            position_timeseries.portfolio_id == PortfolioAggregationJob.portfolio_id,
            position_timeseries.security_id == snapshot.security_id,
            position_timeseries.date == snapshot.date,
            position_timeseries.epoch == snapshot.epoch,
            position_timeseries.updated_at >= snapshot.updated_at,
        )
        .correlate(PortfolioAggregationJob, snapshot)
        .exists()
    )
    return (
        select(1)
        .where(
            snapshot.portfolio_id == PortfolioAggregationJob.portfolio_id,
            snapshot.date <= PortfolioAggregationJob.aggregation_date,
            ~newer_snapshot_exists,
            or_(snapshot.epoch > target_epoch, ~materialized_snapshot_exists),
        )
        .correlate(PortfolioAggregationJob)
        .exists()
    )


def _expired_job_leases_update(job_ids: list[int]):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id.in_(job_ids),
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.lease_expires_at <= func.clock_timestamp(),
    )


def _owned_claim_update(*, job_id: int, lease_token: str):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id == job_id,
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.lease_token == lease_token,
        PortfolioAggregationJob.lease_expires_at > func.clock_timestamp(),
    )


def _cleared_lease_values() -> dict[str, None]:
    return {
        PortfolioAggregationJob.lease_owner.key: None,
        PortfolioAggregationJob.lease_token.key: None,
        PortfolioAggregationJob.lease_expires_at.key: None,
    }
