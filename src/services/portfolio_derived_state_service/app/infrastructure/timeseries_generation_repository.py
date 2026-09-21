"""SQLAlchemy persistence for position timeseries generation."""

import hashlib
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Sequence, cast

from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    DailyPositionValuationReceiptRecord,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PositionHistory,
    PositionTimeseries,
)
from portfolio_common.domain.calculation_lineage import calculation_lineage_from_payload
from portfolio_common.domain.tenant import TenantId
from portfolio_common.durable_correlation import durable_correlation_diagnostics
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.infrastructure.persistence.timeseries_market_data_reader import (
    TimeseriesMarketDataReader,
)
from portfolio_common.infrastructure.persistence.timeseries_upsert_statements import (
    build_position_timeseries_upsert_statement,
)
from portfolio_common.monitoring import observe_control_queue_outcome
from portfolio_common.portfolio_aggregation_job_schema import (
    PortfolioSelectedHistoryObservation,
    PortfolioSelectedHistoryValuationState,
)
from portfolio_common.utils import async_timed
from sqlalchemy import String, Table, and_, case, delete, func, literal, or_, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.postgresql.dml import Insert as PgInsert

from ..domain.position_timeseries.models import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
    PositionTimeseriesRecord,
)
from .selected_history_batch import (
    normalized_history_security_id,
    promote_selected_history_dates,
    ranked_selected_history_source,
    selected_history_source_fact,
)
from .selected_history_valuation import selected_fact_valuation_outcome_handled

logger = logging.getLogger(__name__)

_PORTFOLIO_AGGREGATION_MUTATION_LOCK_NAMESPACE = "lotus-core:portfolio-aggregation-mutation:v1"


class TimeseriesGenerationRepository(TimeseriesMarketDataReader):
    """Persist generated position timeseries and read their source data."""

    async def get_position_snapshot(
        self,
        snapshot_id: int,
        *,
        fallback_epoch: int,
    ) -> PositionSnapshotRecord | None:
        """Load one persisted valuation snapshot as an immutable domain record."""

        result = await self.db.execute(
            select(
                DailyPositionSnapshot,
                DailyPositionValuationReceiptRecord.calculation_lineage,
            )
            .outerjoin(
                DailyPositionValuationReceiptRecord,
                DailyPositionValuationReceiptRecord.snapshot_id == DailyPositionSnapshot.id,
            )
            .where(DailyPositionSnapshot.id == snapshot_id)
        )
        row = result.first()
        return (
            _joined_position_snapshot_record(row, fallback_epoch=fallback_epoch)
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
            logger.debug(
                "Staged position time-series upsert.",
                extra={
                    "security_id": timeseries_record.security_id,
                    "valuation_date": timeseries_record.date.isoformat(),
                },
            )
        except Exception as exc:
            logger.error("Failed to stage upsert for position time series: %s", exc, exc_info=True)
            raise

    async def acquire_portfolio_aggregation_mutation_fence(
        self,
        portfolio_id: str,
    ) -> None:
        """Fence cross-security writes to portfolio-owned derived state until commit."""

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        lock_key = _portfolio_aggregation_mutation_lock_key(normalized_portfolio_id)
        await self.db.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def invalidate_numeric_materializations(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> set[date]:
        """Remove position and portfolio outputs derived from unavailable valuation."""

        normalized_dates = sorted(set(dates))
        if not normalized_dates:
            return set()
        position_result = await self.db.execute(
            delete(PositionTimeseries)
            .where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.security_id == security_id,
                PositionTimeseries.date.in_(normalized_dates),
                PositionTimeseries.epoch == epoch,
            )
            .returning(PositionTimeseries.date)
        )
        portfolio_result = await self.db.execute(
            delete(PortfolioTimeseries)
            .where(
                PortfolioTimeseries.portfolio_id == portfolio_id,
                PortfolioTimeseries.date.in_(normalized_dates),
                PortfolioTimeseries.epoch == epoch,
            )
            .returning(PortfolioTimeseries.date)
        )
        invalidated_dates = {
            cast(date, row[0])
            for result in (position_result, portfolio_result)
            for row in result.fetchall()
        }
        logger.warning(
            "Invalidated timeseries derived from unavailable position valuation.",
            extra={
                "portfolio_id": portfolio_id,
                "security_id": security_id,
                "invalidated_day_count": len(invalidated_dates),
                "epoch": epoch,
            },
        )
        return invalidated_dates

    async def invalidate_portfolio_materializations_in_carry_forward_interval(
        self,
        portfolio_id: str,
        *,
        start_date: date,
        end_date_exclusive: date | None,
        excluded_dates: list[date],
        epoch: int,
    ) -> int:
        """Fail closed for portfolio outputs that depend on unavailable position state."""

        if epoch < 0:
            raise ValueError("Portfolio timeseries epoch cannot be negative.")
        if end_date_exclusive is not None and end_date_exclusive <= start_date:
            return 0

        normalized_excluded_dates = sorted(set(excluded_dates))
        predicates = [
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date >= start_date,
            PortfolioTimeseries.epoch == epoch,
        ]
        if end_date_exclusive is not None:
            predicates.append(PortfolioTimeseries.date < end_date_exclusive)
        if normalized_excluded_dates:
            predicates.append(PortfolioTimeseries.date.not_in(normalized_excluded_dates))

        result = await self.db.execute(delete(PortfolioTimeseries).where(*predicates))
        invalidated_count = int(result.rowcount or 0)
        logger.warning(
            "Invalidated portfolio time-series in an unavailable valuation interval.",
            extra={
                "portfolio_id": portfolio_id,
                "portfolio_date_from": start_date.isoformat(),
                "portfolio_date_to_exclusive": (
                    end_date_exclusive.isoformat() if end_date_exclusive else None
                ),
                "excluded_materialized_day_count": len(normalized_excluded_dates),
                "invalidated_day_count": invalidated_count,
                "epoch": epoch,
            },
        )
        return invalidated_count

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
            select(
                DailyPositionSnapshot,
                DailyPositionValuationReceiptRecord.calculation_lineage,
            )
            .outerjoin(
                DailyPositionValuationReceiptRecord,
                DailyPositionValuationReceiptRecord.snapshot_id == DailyPositionSnapshot.id,
            )
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
        row = result.first()
        return _joined_position_snapshot_record(row) if row is not None else None

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
            select(
                DailyPositionSnapshot,
                DailyPositionValuationReceiptRecord.calculation_lineage,
            )
            .join(ranked_future_snapshots, DailyPositionSnapshot.id == ranked_future_snapshots.c.id)
            .outerjoin(
                DailyPositionValuationReceiptRecord,
                DailyPositionValuationReceiptRecord.snapshot_id == DailyPositionSnapshot.id,
            )
            .where(ranked_future_snapshots.c.rn == 1)
            .order_by(DailyPositionSnapshot.date.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = cast(list[Sequence[object]], result.all())
        return [_joined_position_snapshot_record(row) for row in rows]

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
        target_epoch: int,
        correlation_id: str | None,
    ) -> None:
        """Idempotently stage every materially affected portfolio day at its source epoch."""

        normalized_dates = sorted(set(aggregation_dates))
        if not normalized_dates:
            return
        if target_epoch < 0:
            raise ValueError("Aggregation target epoch cannot be negative.")
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        source_portfolio_id, tenant_id = await self._required_portfolio_authority(
            normalized_portfolio_id
        )

        insert_values = []
        for aggregation_date in normalized_dates:
            diagnostics = durable_correlation_diagnostics(
                correlation_id=correlation_id,
                record_family="aggregation_job",
                portfolio_id=source_portfolio_id,
                aggregation_date=aggregation_date,
            )
            insert_values.append(
                {
                    "tenant_id": tenant_id.value,
                    "portfolio_id": source_portfolio_id,
                    "aggregation_date": aggregation_date,
                    "status": "PENDING",
                    "target_epoch": target_epoch,
                    "source_revision": 1,
                    "correlation_id": diagnostics.correlation_id,
                    "correlation_missing_reason": diagnostics.correlation_missing_reason,
                    "alternate_lookup_key": diagnostics.alternate_lookup_key,
                }
            )

        normalized_correlation_id = insert_values[0]["correlation_id"]
        insert_statement = pg_insert(PortfolioAggregationJob).values(insert_values)
        result = await self.db.execute(
            insert_statement.on_conflict_do_update(
                index_elements=["tenant_id", "portfolio_id", "aggregation_date"],
                set_={
                    "target_epoch": func.greatest(
                        PortfolioAggregationJob.target_epoch,
                        insert_statement.excluded.target_epoch,
                    ),
                    "source_revision": PortfolioAggregationJob.source_revision + 1,
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
                    PortfolioAggregationJob.target_epoch != insert_statement.excluded.target_epoch,
                    PortfolioAggregationJob.status != "PENDING",
                    func.coalesce(PortfolioAggregationJob.correlation_id, "")
                    != (normalized_correlation_id or ""),
                ),
            ).returning(
                PortfolioAggregationJob.status,
                PortfolioAggregationJob.attempt_count,
                PortfolioAggregationJob.source_revision,
            )
        )
        staged_rows = result.fetchall()
        _observe_aggregation_staging_outcomes(
            staged_rows=staged_rows,
            requested_count=len(normalized_dates),
        )
        logger.debug(
            "Staged portfolio aggregation jobs.",
            extra={
                "aggregation_job_count": len(normalized_dates),
                "portfolio_id": normalized_portfolio_id,
                "aggregation_date_from": normalized_dates[0].isoformat(),
                "aggregation_date_to": normalized_dates[-1].isoformat(),
                "target_epoch": target_epoch,
            },
        )

    async def promote_selected_history_aggregation_jobs_for_dates(
        self,
        portfolio_id: str,
        *,
        security_id: str,
        as_of_dates: list[date],
        target_epoch: int,
        correlation_id: str | None,
        valuation_outcome: Literal["READY", "UNAVAILABLE"] | None = None,
        valuation_date: date | None = None,
    ) -> int:
        """Prepare one selected-history batch for all newly swept affected days."""

        if not as_of_dates:
            return 0
        if target_epoch < 0:
            raise ValueError("Aggregation target epoch cannot be negative.")
        if not security_id.strip():
            raise ValueError("Selected-history security id cannot be blank.")
        if valuation_outcome not in (None, "READY", "UNAVAILABLE"):
            raise ValueError("Selected-history valuation outcome is not supported.")
        if (valuation_outcome is None) != (valuation_date is None):
            raise ValueError("Selected-history valuation outcome requires its source date.")
        source_portfolio_id, tenant_id = await self._required_portfolio_authority(portfolio_id)
        return await promote_selected_history_dates(
            self.db,
            promote_one=self.promote_selected_history_aggregation_jobs,
            portfolio_id=source_portfolio_id,
            tenant_id=tenant_id.value,
            security_id=security_id,
            as_of_dates=as_of_dates,
            target_epoch=target_epoch,
            correlation_id=correlation_id,
            valuation_outcome=valuation_outcome,
            valuation_date=valuation_date,
        )

    async def promote_selected_history_aggregation_jobs(
        self,
        portfolio_id: str,
        *,
        security_id: str,
        as_of_date: date,
        target_epoch: int,
        correlation_id: str | None,
        valuation_outcome: Literal["READY", "UNAVAILABLE"] | None = None,
        valuation_date: date | None = None,
        selected_history_rows: Table | None = None,
    ) -> int:
        """Rearm selected history dates under the caller's portfolio mutation fence.

        A durable day/epoch marker pays for the full portfolio selection once. Later
        same-epoch snapshots still check their own indexed latest history so a late
        security fact cannot be hidden by the marker. Closed positions never fall
        back to an older non-zero row.
        """

        if target_epoch < 0:
            raise ValueError("Aggregation target epoch cannot be negative.")
        if not security_id.strip():
            raise ValueError("Selected-history security id cannot be blank.")
        if valuation_outcome not in (None, "READY", "UNAVAILABLE"):
            raise ValueError("Selected-history valuation outcome is not supported.")
        if (valuation_outcome is None) != (valuation_date is None):
            raise ValueError("Selected-history valuation outcome requires its source date.")
        source_portfolio_id, tenant_id = await self._required_portfolio_authority(portfolio_id)
        anchor = (
            await self.db.execute(
                select(
                    PortfolioAggregationJob.selected_history_sweep_epoch,
                    PortfolioAggregationJob.selected_history_collective_epoch,
                )
                .where(
                    PortfolioAggregationJob.tenant_id == tenant_id.value,
                    PortfolioAggregationJob.portfolio_id == source_portfolio_id,
                    PortfolioAggregationJob.aggregation_date == as_of_date,
                )
                .with_for_update()
            )
        ).one_or_none()
        if anchor is None:
            raise RuntimeError("Selected-history sweep requires a staged aggregation day.")
        full_sweep = anchor[0] < target_epoch
        diagnostics = durable_correlation_diagnostics(
            correlation_id=correlation_id,
            record_family="aggregation_job",
            portfolio_id=source_portfolio_id,
            aggregation_date=as_of_date,
        )
        if full_sweep:
            ranked = ranked_selected_history_source(
                portfolio_id=source_portfolio_id,
                as_of_date=as_of_date,
                selected_history_rows=selected_history_rows,
            )
            selected = (
                select(
                    ranked.c.security_id,
                    ranked.c.history_id,
                    ranked.c.business_date,
                    ranked.c.epoch,
                    ranked.c.source_fact,
                    func.max(ranked.c.epoch).over().label("collective_epoch"),
                )
                .where(ranked.c.rank == 1, ranked.c.quantity != 0)
                .cte("selected_position_history")
            )
            # A higher-epoch sweep can replace a previously selected holding
            # with a close (or another fact). The current non-zero selection
            # alone cannot name the former business-date control. Read the
            # prior observation before the upsert below replaces it.
            previous_selected_dates = (
                select(
                    PortfolioSelectedHistoryObservation.selected_business_date.label(
                        "business_date"
                    )
                )
                .select_from(PortfolioSelectedHistoryObservation)
                .outerjoin(
                    ranked,
                    and_(
                        ranked.c.security_id == PortfolioSelectedHistoryObservation.security_id,
                        ranked.c.rank == 1,
                    ),
                )
                .where(
                    PortfolioSelectedHistoryObservation.tenant_id == tenant_id.value,
                    PortfolioSelectedHistoryObservation.portfolio_id == source_portfolio_id,
                    PortfolioSelectedHistoryObservation.as_of_date == as_of_date,
                    PortfolioSelectedHistoryObservation.selected_nonzero.is_(True),
                    PortfolioSelectedHistoryObservation.selected_business_date.is_not(None),
                    or_(
                        ranked.c.history_id.is_(None),
                        ranked.c.history_id.is_distinct_from(
                            PortfolioSelectedHistoryObservation.position_history_id
                        ),
                        ranked.c.business_date.is_distinct_from(
                            PortfolioSelectedHistoryObservation.selected_business_date
                        ),
                        ranked.c.source_fact.is_distinct_from(
                            PortfolioSelectedHistoryObservation.source_fact
                        ),
                        ranked.c.quantity == 0,
                    ),
                )
                .cte("previous_selected_history_dates")
            )
            promoted_dates = (
                select(selected.c.business_date)
                .union(select(previous_selected_dates.c.business_date))
                .cte("selected_history_dates_to_promote")
            )
            # The first post-migration sweep has no observation for a selected
            # fact. Re-arm an equal-epoch historical control only for facts not
            # observed by any earlier affected boundary; new daily sweeps of
            # identical history then do not repeat historical aggregation work.
            fact_scope = (
                PortfolioSelectedHistoryObservation.tenant_id == tenant_id.value,
                PortfolioSelectedHistoryObservation.portfolio_id == source_portfolio_id,
                PortfolioSelectedHistoryObservation.security_id == selected.c.security_id,
                PortfolioSelectedHistoryObservation.position_history_id == selected.c.history_id,
                PortfolioSelectedHistoryObservation.selected_business_date
                == selected.c.business_date,
                PortfolioSelectedHistoryObservation.selected_nonzero.is_(True),
                PortfolioSelectedHistoryObservation.source_fact == selected.c.source_fact,
            )
            previously_observed = (
                select(literal(1))
                .select_from(PortfolioSelectedHistoryObservation)
                .where(*fact_scope)
                .exists()
            )
            valuation_outcome_current = selected_fact_valuation_outcome_handled(
                tenant_id=tenant_id.value,
                portfolio_id=source_portfolio_id,
                selected=selected,
                valuation_outcome=valuation_outcome,
                delivered_epoch=target_epoch,
                delivered_date=valuation_date,
            )
            # Selection can precede valuation. READY/UNAVAILABLE transitions
            # rearm once; repeated daily outcomes for the same fact do not.
            current_security = and_(
                selected.c.security_id == security_id.strip(),
                selected.c.epoch <= target_epoch,
                selected.c.business_date <= valuation_date
                if valuation_date is not None
                else literal(False),
            )
            unobserved_dates = select(selected.c.business_date).where(
                or_(~previously_observed, and_(current_security, ~valuation_outcome_current))
                if valuation_outcome is not None
                else ~previously_observed
            )
            changed_dates = unobserved_dates.union(select(previous_selected_dates.c.business_date))
            collective_epoch = (
                await self.db.execute(select(func.max(selected.c.collective_epoch)))
            ).scalar_one_or_none()
            effective_epoch = max(target_epoch, collective_epoch or 0)
            alternate_key = (
                literal("aggregation_job|aggregation_date=")
                + sql_cast(promoted_dates.c.business_date, String)
                + literal(f"|portfolio_id={source_portfolio_id}")
            )
            insert_statement = pg_insert(PortfolioAggregationJob).from_select(
                [
                    "tenant_id",
                    "portfolio_id",
                    "aggregation_date",
                    "status",
                    "target_epoch",
                    "source_revision",
                    "correlation_id",
                    "correlation_missing_reason",
                    "alternate_lookup_key",
                ],
                select(
                    literal(tenant_id.value),
                    literal(source_portfolio_id),
                    promoted_dates.c.business_date,
                    literal("PENDING"),
                    literal(effective_epoch),
                    literal(1),
                    literal(diagnostics.correlation_id),
                    literal(diagnostics.correlation_missing_reason),
                    alternate_key if diagnostics.correlation_id is None else literal(None),
                ).select_from(promoted_dates),
            )
        else:
            latest = await self._latest_selected_history_for_security(
                portfolio_id=source_portfolio_id,
                security_id=security_id.strip(),
                as_of_date=as_of_date,
            )
            observation = await self.db.scalar(
                select(PortfolioSelectedHistoryObservation)
                .where(
                    PortfolioSelectedHistoryObservation.tenant_id == tenant_id.value,
                    PortfolioSelectedHistoryObservation.portfolio_id == source_portfolio_id,
                    PortfolioSelectedHistoryObservation.as_of_date == as_of_date,
                    PortfolioSelectedHistoryObservation.security_id == security_id.strip(),
                )
                .with_for_update()
            )
            if latest is None and observation is None:
                return 0
            latest_identity = (
                (latest.id, latest.position_date, latest.quantity != 0, latest.source_fact)
                if latest is not None
                else (None, None, False, None)
            )
            selected_valuation_outcome = (
                valuation_outcome
                if latest is not None
                and valuation_date is not None
                and latest.epoch <= target_epoch
                and latest.position_date <= valuation_date
                else None
            )
            observed_identity = (
                (
                    observation.position_history_id,
                    observation.selected_business_date,
                    observation.selected_nonzero,
                    observation.source_fact,
                )
                if observation is not None
                else (None, None, False, None)
            )
            if latest_identity == observed_identity and (
                selected_valuation_outcome is None or not latest_identity[2]
            ):
                return 0
            previously_observed_nonzero_fact = False
            valuation_outcome_current = False
            if latest is not None and latest.quantity != 0:
                fact_scope = (
                    PortfolioSelectedHistoryObservation.tenant_id == tenant_id.value,
                    PortfolioSelectedHistoryObservation.portfolio_id == source_portfolio_id,
                    PortfolioSelectedHistoryObservation.security_id == security_id.strip(),
                    PortfolioSelectedHistoryObservation.position_history_id == latest.id,
                    PortfolioSelectedHistoryObservation.selected_business_date
                    == latest.position_date,
                    PortfolioSelectedHistoryObservation.selected_nonzero.is_(True),
                    PortfolioSelectedHistoryObservation.source_fact == latest.source_fact,
                )
                previously_observed_nonzero_fact = bool(
                    await self.db.scalar(
                        select(literal(1))
                        .select_from(PortfolioSelectedHistoryObservation)
                        .where(*fact_scope)
                        .limit(1)
                    )
                )
                if selected_valuation_outcome is not None:
                    valuation_outcome_current = await self._selected_valuation_outcome_current(
                        tenant_id=tenant_id.value,
                        portfolio_id=source_portfolio_id,
                        security_id=security_id.strip(),
                        latest=latest,
                        delivered_epoch=target_epoch,
                        delivered_date=cast(date, valuation_date),
                        valuation_outcome=selected_valuation_outcome,
                    )
            if latest_identity == observed_identity and valuation_outcome_current:
                await self._persist_targeted_history_valuation_outcome(
                    tenant_id=tenant_id.value,
                    portfolio_id=source_portfolio_id,
                    security_id=security_id.strip(),
                    latest=latest,
                    delivered_epoch=target_epoch,
                    valuation_date=valuation_date,
                    valuation_outcome=selected_valuation_outcome,
                )
                return 0
            observation_insert = pg_insert(PortfolioSelectedHistoryObservation).values(
                tenant_id=tenant_id.value,
                portfolio_id=source_portfolio_id,
                as_of_date=as_of_date,
                security_id=security_id.strip(),
                position_history_id=latest_identity[0],
                selected_business_date=latest_identity[1],
                selected_nonzero=latest_identity[2],
                source_fact=latest_identity[3],
            )
            await self.db.execute(
                observation_insert.on_conflict_do_update(
                    index_elements=[
                        "tenant_id",
                        "portfolio_id",
                        "as_of_date",
                        "security_id",
                    ],
                    set_={
                        "position_history_id": observation_insert.excluded.position_history_id,
                        "selected_business_date": (
                            observation_insert.excluded.selected_business_date
                        ),
                        "selected_nonzero": observation_insert.excluded.selected_nonzero,
                        "source_fact": observation_insert.excluded.source_fact,
                    },
                )
            )
            await self._persist_targeted_history_valuation_outcome(
                tenant_id=tenant_id.value,
                portfolio_id=source_portfolio_id,
                security_id=security_id.strip(),
                latest=latest,
                delivered_epoch=target_epoch,
                valuation_date=valuation_date,
                valuation_outcome=selected_valuation_outcome,
            )
            effective_epoch = max(target_epoch, anchor[1], latest.epoch if latest else 0)
            affected_dates = {
                selected_date
                for selected_date, selected_nonzero in (
                    (observed_identity[1], observed_identity[2]),
                    (latest_identity[1], latest_identity[2]),
                )
                if selected_nonzero and selected_date is not None
            }
            if not affected_dates:
                return 0
            insert_statement = pg_insert(PortfolioAggregationJob).values(
                [
                    {
                        "tenant_id": tenant_id.value,
                        "portfolio_id": source_portfolio_id,
                        "aggregation_date": selected_date,
                        "status": "PENDING",
                        "target_epoch": effective_epoch,
                        "source_revision": 1,
                        "correlation_id": diagnostics.correlation_id,
                        "correlation_missing_reason": diagnostics.correlation_missing_reason,
                        "alternate_lookup_key": (
                            f"aggregation_job|aggregation_date={selected_date.isoformat()}"
                            f"|portfolio_id={source_portfolio_id}"
                            if diagnostics.correlation_id is None
                            else None
                        ),
                    }
                    for selected_date in sorted(affected_dates)
                ]
            )
        promotion_conflict = (
            PortfolioAggregationJob.target_epoch < insert_statement.excluded.target_epoch
        )
        if full_sweep:
            promotion_conflict = or_(
                promotion_conflict,
                and_(
                    insert_statement.excluded.aggregation_date != as_of_date,
                    PortfolioAggregationJob.target_epoch == insert_statement.excluded.target_epoch,
                    PortfolioAggregationJob.aggregation_date.in_(changed_dates),
                ),
            )
        else:
            if not previously_observed_nonzero_fact or (
                selected_valuation_outcome is not None and not valuation_outcome_current
            ):
                promotion_conflict = or_(
                    promotion_conflict,
                    and_(
                        insert_statement.excluded.aggregation_date != as_of_date,
                        PortfolioAggregationJob.target_epoch
                        == insert_statement.excluded.target_epoch,
                    ),
                )
        result = await self.db.execute(
            insert_statement.on_conflict_do_update(
                index_elements=["tenant_id", "portfolio_id", "aggregation_date"],
                set_={
                    "target_epoch": insert_statement.excluded.target_epoch,
                    "source_revision": PortfolioAggregationJob.source_revision + 1,
                    "status": case(
                        (PortfolioAggregationJob.status == "PROCESSING", "PROCESSING"),
                        else_="PENDING",
                    ),
                    "failure_reason": case(
                        (PortfolioAggregationJob.status == "PROCESSING", "REPROCESS_REQUESTED"),
                        else_=None,
                    ),
                    "correlation_id": insert_statement.excluded.correlation_id,
                    "correlation_missing_reason": (
                        insert_statement.excluded.correlation_missing_reason
                    ),
                    "alternate_lookup_key": insert_statement.excluded.alternate_lookup_key,
                    "updated_at": func.now(),
                },
                where=promotion_conflict,
            ).returning(PortfolioAggregationJob.id)
        )
        affected_count = len(result.fetchall())
        if full_sweep:
            observation_insert = pg_insert(PortfolioSelectedHistoryObservation).from_select(
                [
                    "tenant_id",
                    "portfolio_id",
                    "as_of_date",
                    "security_id",
                    "position_history_id",
                    "selected_business_date",
                    "selected_nonzero",
                    "source_fact",
                ],
                select(
                    literal(tenant_id.value),
                    literal(source_portfolio_id),
                    literal(as_of_date),
                    ranked.c.security_id,
                    ranked.c.history_id,
                    ranked.c.business_date,
                    ranked.c.quantity != 0,
                    ranked.c.source_fact,
                ).where(ranked.c.rank == 1),
            )
            await self.db.execute(
                observation_insert.on_conflict_do_update(
                    index_elements=[
                        "tenant_id",
                        "portfolio_id",
                        "as_of_date",
                        "security_id",
                    ],
                    set_={
                        "position_history_id": observation_insert.excluded.position_history_id,
                        "selected_business_date": (
                            observation_insert.excluded.selected_business_date
                        ),
                        "selected_nonzero": observation_insert.excluded.selected_nonzero,
                        "source_fact": observation_insert.excluded.source_fact,
                    },
                )
            )
            await self._persist_swept_history_valuation_outcome(
                tenant_id=tenant_id.value,
                portfolio_id=source_portfolio_id,
                security_id=security_id.strip(),
                as_of_date=as_of_date,
                delivered_epoch=target_epoch,
                valuation_date=valuation_date,
                valuation_outcome=valuation_outcome,
                selected_history_rows=selected_history_rows,
            )
            await self.db.execute(
                update(PortfolioAggregationJob)
                .where(
                    PortfolioAggregationJob.tenant_id == tenant_id.value,
                    PortfolioAggregationJob.portfolio_id == source_portfolio_id,
                    PortfolioAggregationJob.aggregation_date == as_of_date,
                )
                .values(
                    selected_history_sweep_epoch=target_epoch,
                    selected_history_collective_epoch=effective_epoch,
                )
            )
        elif effective_epoch > anchor[1]:
            await self.db.execute(
                update(PortfolioAggregationJob)
                .where(
                    PortfolioAggregationJob.tenant_id == tenant_id.value,
                    PortfolioAggregationJob.portfolio_id == source_portfolio_id,
                    PortfolioAggregationJob.aggregation_date == as_of_date,
                )
                .values(selected_history_collective_epoch=effective_epoch)
            )
        return affected_count

    async def _selected_valuation_outcome_current(
        self,
        *,
        tenant_id: str,
        portfolio_id: str,
        security_id: str,
        latest: Any,
        delivered_epoch: int,
        delivered_date: date,
        valuation_outcome: Literal["READY", "UNAVAILABLE"],
    ) -> bool:
        state = PortfolioSelectedHistoryValuationState
        existing = await self.db.scalar(
            select(state).where(
                state.tenant_id == tenant_id,
                state.portfolio_id == portfolio_id,
                state.security_id == security_id,
                state.position_history_id == latest.id,
            )
        )
        return bool(
            existing is not None
            and existing.source_fact == latest.source_fact
            and existing.selected_business_date == latest.position_date
            and (
                existing.valuation_outcome == valuation_outcome
                or (existing.valuation_epoch, existing.valuation_date)
                > (delivered_epoch, delivered_date)
            )
        )

    async def _latest_selected_history_for_security(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        as_of_date: date,
    ) -> Any:
        return (
            await self.db.execute(
                select(
                    PositionHistory.id,
                    PositionHistory.position_date,
                    PositionHistory.epoch,
                    PositionHistory.quantity,
                    selected_history_source_fact().label("source_fact"),
                )
                .where(
                    PositionHistory.portfolio_id == portfolio_id,
                    normalized_history_security_id() == security_id,
                    PositionHistory.position_date <= as_of_date,
                )
                .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
                .limit(1)
            )
        ).one_or_none()

    async def _persist_swept_history_valuation_outcome(
        self,
        *,
        tenant_id: str,
        portfolio_id: str,
        security_id: str,
        as_of_date: date,
        delivered_epoch: int,
        valuation_date: date | None,
        valuation_outcome: Literal["READY", "UNAVAILABLE"] | None,
        selected_history_rows: Table | None,
    ) -> None:
        if valuation_outcome is None:
            return
        latest = (
            (
                await self.db.execute(
                    select(
                        selected_history_rows.c.history_id.label("id"),
                        selected_history_rows.c.business_date.label("position_date"),
                        selected_history_rows.c.epoch,
                        selected_history_rows.c.quantity,
                        selected_history_rows.c.source_fact,
                    ).where(
                        selected_history_rows.c.as_of_date == as_of_date,
                        selected_history_rows.c.security_id == security_id,
                    )
                )
            ).one_or_none()
            if selected_history_rows is not None
            else await self._latest_selected_history_for_security(
                portfolio_id=portfolio_id,
                security_id=security_id,
                as_of_date=as_of_date,
            )
        )
        await self._persist_targeted_history_valuation_outcome(
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            latest=latest,
            delivered_epoch=delivered_epoch,
            valuation_date=valuation_date,
            valuation_outcome=valuation_outcome,
        )

    async def _persist_targeted_history_valuation_outcome(
        self,
        *,
        tenant_id: str,
        portfolio_id: str,
        security_id: str,
        latest: Any,
        delivered_epoch: int,
        valuation_date: date | None,
        valuation_outcome: Literal["READY", "UNAVAILABLE"] | None,
    ) -> None:
        if (
            valuation_outcome is None
            or valuation_date is None
            or latest is None
            or latest.quantity == 0
            or latest.epoch > delivered_epoch
            or latest.position_date > valuation_date
        ):
            return
        state_insert = pg_insert(PortfolioSelectedHistoryValuationState).values(
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            position_history_id=latest.id,
            selected_business_date=latest.position_date,
            source_fact=latest.source_fact,
            valuation_outcome=valuation_outcome,
            valuation_epoch=delivered_epoch,
            valuation_date=valuation_date,
        )
        await self._upsert_selected_history_valuation_state(state_insert)

    async def _upsert_selected_history_valuation_state(self, state_insert: PgInsert) -> None:
        await self.db.execute(
            state_insert.on_conflict_do_update(
                index_elements=[
                    "tenant_id",
                    "portfolio_id",
                    "security_id",
                    "position_history_id",
                ],
                set_={
                    "selected_business_date": state_insert.excluded.selected_business_date,
                    "source_fact": state_insert.excluded.source_fact,
                    "valuation_outcome": state_insert.excluded.valuation_outcome,
                    "valuation_epoch": state_insert.excluded.valuation_epoch,
                    "valuation_date": state_insert.excluded.valuation_date,
                },
                where=and_(
                    or_(
                        PortfolioSelectedHistoryValuationState.valuation_epoch
                        < state_insert.excluded.valuation_epoch,
                        and_(
                            PortfolioSelectedHistoryValuationState.valuation_epoch
                            == state_insert.excluded.valuation_epoch,
                            PortfolioSelectedHistoryValuationState.valuation_date
                            <= state_insert.excluded.valuation_date,
                        ),
                    ),
                    or_(
                        PortfolioSelectedHistoryValuationState.selected_business_date
                        != state_insert.excluded.selected_business_date,
                        PortfolioSelectedHistoryValuationState.source_fact
                        != state_insert.excluded.source_fact,
                        PortfolioSelectedHistoryValuationState.valuation_outcome
                        != state_insert.excluded.valuation_outcome,
                        PortfolioSelectedHistoryValuationState.valuation_epoch
                        != state_insert.excluded.valuation_epoch,
                        PortfolioSelectedHistoryValuationState.valuation_date
                        != state_insert.excluded.valuation_date,
                    ),
                ),
            )
        )

    async def restage_aggregation_jobs_in_carry_forward_interval(
        self,
        portfolio_id: str,
        *,
        start_date: date,
        end_date_exclusive: date | None,
        excluded_dates: list[date],
        target_epoch: int,
        correlation_id: str | None,
    ) -> list[date]:
        """Restage and return exact existing days carrying changed position state."""

        if target_epoch < 0:
            raise ValueError("Aggregation target epoch cannot be negative.")
        if end_date_exclusive is not None and end_date_exclusive <= start_date:
            return []
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        source_portfolio_id, tenant_id = await self._required_portfolio_authority(
            normalized_portfolio_id
        )
        normalized_excluded_dates = sorted(set(excluded_dates))
        predicates = [
            PortfolioAggregationJob.tenant_id == tenant_id.value,
            PortfolioAggregationJob.portfolio_id == source_portfolio_id,
            PortfolioAggregationJob.aggregation_date >= start_date,
            PortfolioAggregationJob.status.in_(("PENDING", "PROCESSING", "COMPLETE", "FAILED")),
        ]
        if end_date_exclusive is not None:
            predicates.append(PortfolioAggregationJob.aggregation_date < end_date_exclusive)
        if normalized_excluded_dates:
            predicates.append(
                PortfolioAggregationJob.aggregation_date.not_in(normalized_excluded_dates)
            )

        interval_correlation = durable_correlation_diagnostics(
            correlation_id=correlation_id,
            record_family="aggregation_carry_forward_interval",
            portfolio_id=source_portfolio_id,
            start_date=start_date,
            end_date_exclusive=end_date_exclusive,
        ).correlation_id
        values: dict[str, Any] = {
            "target_epoch": func.greatest(
                PortfolioAggregationJob.target_epoch,
                target_epoch,
            ),
            "source_revision": PortfolioAggregationJob.source_revision + 1,
            "status": case(
                (
                    PortfolioAggregationJob.status == "PROCESSING",
                    PortfolioAggregationJob.status,
                ),
                else_="PENDING",
            ),
            "failure_reason": case(
                (
                    PortfolioAggregationJob.status == "PROCESSING",
                    "REPROCESS_REQUESTED",
                ),
                else_=None,
            ),
            "updated_at": func.now(),
        }
        if interval_correlation is not None:
            values.update(
                {
                    "correlation_id": interval_correlation,
                    "correlation_missing_reason": None,
                    "alternate_lookup_key": None,
                }
            )

        result = await self.db.execute(
            update(PortfolioAggregationJob)
            .where(*predicates)
            .values(**values)
            .returning(PortfolioAggregationJob.aggregation_date)
        )
        restaged_dates = sorted(result.scalars().all())
        restaged_count = len(restaged_dates)
        observe_control_queue_outcome(
            "aggregation",
            "carry_forward_staging",
            "restaged",
            restaged_count,
        )
        logger.debug(
            "Restaged portfolio aggregation jobs in a carry-forward interval.",
            extra={
                "portfolio_id": normalized_portfolio_id,
                "aggregation_date_from": start_date.isoformat(),
                "aggregation_date_to_exclusive": (
                    end_date_exclusive.isoformat() if end_date_exclusive else None
                ),
                "excluded_materialized_day_count": len(normalized_excluded_dates),
                "target_epoch": target_epoch,
                "restaged_job_count": restaged_count,
            },
        )
        return restaged_dates

    async def _required_portfolio_authority(self, portfolio_id: str) -> tuple[str, TenantId]:
        """Resolve the durable portfolio identity and tenant before staging owned work."""

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        result = await self.db.execute(
            select(Portfolio.portfolio_id, Portfolio.tenant_id).where(
                func.trim(Portfolio.portfolio_id) == normalized_portfolio_id
            )
        )
        source_authority = result.one_or_none()
        if source_authority is None:
            raise LookupError(
                f"Portfolio {normalized_portfolio_id!r} has no durable tenant authority."
            )
        source_portfolio_id, source_tenant_id = source_authority
        return str(source_portfolio_id), TenantId(str(source_tenant_id))


def _observe_aggregation_staging_outcomes(
    *,
    staged_rows: Sequence[Any],
    requested_count: int,
) -> None:
    outcomes = {
        "new": 0,
        "rearmed": 0,
        "superseded": 0,
        "no_op": requested_count - len(staged_rows),
    }
    for row in staged_rows:
        if int(row.source_revision) == 1:
            outcomes["new"] += 1
        elif str(row.status) == "PROCESSING" or int(row.attempt_count) == 0:
            outcomes["superseded"] += 1
        else:
            outcomes["rearmed"] += 1
    for outcome, count in outcomes.items():
        observe_control_queue_outcome("aggregation", "staging", outcome, count)


def _portfolio_aggregation_mutation_lock_key(portfolio_id: str) -> int:
    """Return one stable signed PostgreSQL advisory-lock key for a portfolio."""

    identity = f"{_PORTFOLIO_AGGREGATION_MUTATION_LOCK_NAMESPACE}:{portfolio_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def to_position_snapshot_record(
    row: DailyPositionSnapshot,
    *,
    fallback_epoch: int = 0,
    calculation_lineage_payload: object = None,
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
        valuation_status=str(row.valuation_status),
        source_updated_at=cast(datetime, row.updated_at),
        calculation_lineage=calculation_lineage_from_payload(calculation_lineage_payload),
    )


def _joined_position_snapshot_record(
    row: Sequence[object],
    *,
    fallback_epoch: int = 0,
) -> PositionSnapshotRecord:
    return to_position_snapshot_record(
        cast(DailyPositionSnapshot, row[0]),
        fallback_epoch=fallback_epoch,
        calculation_lineage_payload=row[1],
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
        calculation_lineage=calculation_lineage_from_payload(row.calculation_lineage),
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
        materialized_at=cast(datetime, row.updated_at),
    )
