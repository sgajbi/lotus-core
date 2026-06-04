from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from portfolio_common.database_models import ConsumerDlqEvent as DBConsumerDlqEvent
from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import SQLAlchemyError

from ..DTOs.ingestion_job_dto import IngestionErrorBudgetStatusResponse


def default_error_budget_status(
    *,
    lookback_minutes: int,
    failure_rate_threshold: Decimal,
    dlq_budget_events_per_window: int,
) -> IngestionErrorBudgetStatusResponse:
    return IngestionErrorBudgetStatusResponse(
        lookback_minutes=lookback_minutes,
        previous_lookback_minutes=lookback_minutes,
        total_jobs=0,
        failed_jobs=0,
        failure_rate=Decimal("0"),
        remaining_error_budget=failure_rate_threshold,
        backlog_jobs=0,
        previous_backlog_jobs=0,
        backlog_growth=0,
        replay_backlog_pressure_ratio=Decimal("0"),
        dlq_events_in_window=0,
        dlq_budget_events_per_window=max(1, dlq_budget_events_per_window),
        dlq_pressure_ratio=Decimal("0"),
        breach_failure_rate=False,
        breach_backlog_growth=False,
    )


async def load_error_budget_status_response(
    *,
    lookback_minutes: int,
    failure_rate_threshold: Decimal,
    backlog_growth_threshold: int,
    replay_max_backlog_jobs: int,
    dlq_budget_events_per_window: int,
    session_factory,
    logger: logging.Logger,
) -> IngestionErrorBudgetStatusResponse:
    async for db in session_factory():
        try:
            now_utc = datetime.now(UTC)
            current_since = now_utc - timedelta(minutes=lookback_minutes)
            previous_since = now_utc - timedelta(minutes=lookback_minutes * 2)
            current_row = (
                await db.execute(
                    select(
                        func.count(DBIngestionJob.id).label("total_jobs"),
                        func.sum(case((DBIngestionJob.status == "failed", 1), else_=0)).label(
                            "failed_jobs"
                        ),
                        func.sum(
                            case(
                                (DBIngestionJob.status.in_(["accepted", "queued"]), 1),
                                else_=0,
                            )
                        ).label("backlog_jobs"),
                    ).where(DBIngestionJob.submitted_at >= current_since)
                )
            ).one()
            previous_row = (
                await db.execute(
                    select(
                        func.sum(
                            case(
                                (DBIngestionJob.status.in_(["accepted", "queued"]), 1),
                                else_=0,
                            )
                        ).label("previous_backlog_jobs"),
                    ).where(
                        and_(
                            DBIngestionJob.submitted_at >= previous_since,
                            DBIngestionJob.submitted_at < current_since,
                        )
                    )
                )
            ).one()
            dlq_events_in_window = int(
                (
                    await db.execute(
                        select(func.count(DBConsumerDlqEvent.id)).where(
                            DBConsumerDlqEvent.observed_at >= current_since
                        )
                    )
                ).scalar_one()
                or 0
            )

            total_jobs = int(current_row[0] or 0)
            failed_jobs = int(current_row[1] or 0)
            failure_rate = (
                Decimal(failed_jobs) / Decimal(total_jobs) if total_jobs else Decimal("0")
            )
            remaining_budget = max(Decimal("0"), failure_rate_threshold - failure_rate)
            backlog_jobs = int(current_row[2] or 0)
            previous_backlog_jobs = int(previous_row[0] or 0)
            backlog_growth = backlog_jobs - previous_backlog_jobs
            replay_backlog_pressure_ratio = Decimal(backlog_jobs) / Decimal(
                max(1, replay_max_backlog_jobs)
            )
            dlq_budget_events_per_window = max(1, dlq_budget_events_per_window)
            dlq_pressure_ratio = Decimal(dlq_events_in_window) / Decimal(
                dlq_budget_events_per_window
            )

            return IngestionErrorBudgetStatusResponse(
                lookback_minutes=lookback_minutes,
                previous_lookback_minutes=lookback_minutes,
                total_jobs=total_jobs,
                failed_jobs=failed_jobs,
                failure_rate=failure_rate,
                remaining_error_budget=remaining_budget,
                backlog_jobs=backlog_jobs,
                previous_backlog_jobs=previous_backlog_jobs,
                backlog_growth=backlog_growth,
                replay_backlog_pressure_ratio=replay_backlog_pressure_ratio,
                dlq_events_in_window=dlq_events_in_window,
                dlq_budget_events_per_window=dlq_budget_events_per_window,
                dlq_pressure_ratio=dlq_pressure_ratio,
                breach_failure_rate=failure_rate > failure_rate_threshold,
                breach_backlog_growth=backlog_growth > backlog_growth_threshold,
            )
        except SQLAlchemyError as exc:
            logger.warning(
                "ingestion_error_budget_status_unavailable",
                extra={"lookback_minutes": lookback_minutes},
                exc_info=exc,
            )
            return default_error_budget_status(
                lookback_minutes=lookback_minutes,
                failure_rate_threshold=failure_rate_threshold,
                dlq_budget_events_per_window=dlq_budget_events_per_window,
            )
    return default_error_budget_status(
        lookback_minutes=lookback_minutes,
        failure_rate_threshold=failure_rate_threshold,
        dlq_budget_events_per_window=dlq_budget_events_per_window,
    )
