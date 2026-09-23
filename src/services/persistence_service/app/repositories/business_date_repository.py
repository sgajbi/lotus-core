# src/services/persistence_service/app/repositories/business_date_repository.py
import logging
from datetime import date

from portfolio_common.business_calendar_sql import (
    acquire_default_business_calendar_activation_lock,
)
from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate as DBBusinessDate,
)
from portfolio_common.database_models import (
    PositionHistory,
    PositionState,
)
from portfolio_common.domain.business_calendar import normalize_business_calendar_code
from portfolio_common.events import BusinessDateEvent
from portfolio_common.valuation_job_contracts import ValuationJobUpsert
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _normalized_security_id_expression(column):
    """Match Python ``str.strip`` for legacy identifier reads in PostgreSQL."""

    return func.regexp_replace(column, r"^[[:space:]]+|[[:space:]]+$", "", "g")


class BusinessDateRepository:
    """
    Handles database operations for the BusinessDate model.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_business_date(self, event: BusinessDateEvent) -> None:
        """
        Idempotently creates a business date using a native PostgreSQL
        UPSERT (INSERT ... ON CONFLICT DO NOTHING).
        """
        try:
            if (
                normalize_business_calendar_code(event.calendar_code)
                == DEFAULT_BUSINESS_CALENDAR_CODE
            ):
                await acquire_default_business_calendar_activation_lock(self.db)
            business_date_data = {"date": event.business_date}
            business_date_data["calendar_code"] = event.calendar_code
            business_date_data["market_code"] = event.market_code
            business_date_data["source_system"] = event.source_system
            business_date_data["source_batch_id"] = event.source_batch_id

            stmt = pg_insert(DBBusinessDate).values(**business_date_data)

            # If the date already exists, do nothing. This makes the operation idempotent.
            final_stmt = stmt.on_conflict_do_nothing(
                index_elements=["calendar_code", "date"]
            ).returning(DBBusinessDate.date)

            inserted_date = (await self.db.execute(final_stmt)).scalar_one_or_none()
            if inserted_date is not None:
                await self._stage_default_calendar_valuation_jobs(event)
            logger.debug(
                "Staged business date upsert.",
                extra={
                    "business_date": event.business_date.isoformat(),
                    "inserted": inserted_date is not None,
                },
            )

        except Exception:
            logger.error(
                "Failed to stage business date upsert.",
                extra={"business_date": event.business_date.isoformat()},
                exc_info=True,
            )
            raise

    async def _stage_default_calendar_valuation_jobs(self, event: BusinessDateEvent) -> None:
        """Atomically schedule the exact date newly admitted to valuation.

        A market-price or FX fact may arrive while an interior date is absent from the
        governed calendar. Its replay can legitimately finish before that date is later
        admitted. Scheduling every position open on the newly admitted date closes that
        race without regressing watermarks or invalidating current position-history epochs.
        The job upsert rearms terminal work and asks an in-flight worker to replay after
        its current claim, all in the same transaction as the calendar insert.
        """

        if normalize_business_calendar_code(event.calendar_code) != DEFAULT_BUSINESS_CALENDAR_CODE:
            return

        position_keys = await self._find_open_position_keys(event.business_date)
        if not position_keys:
            return

        source_mutation_id = (
            f"BUSINESS_DATE_ADMISSION:{event.calendar_code}:{event.business_date.isoformat()}"
        )
        await ValuationJobRepository(self.db).upsert_jobs(
            [
                ValuationJobUpsert(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    valuation_date=event.business_date,
                    epoch=epoch,
                    correlation_id=event.correlation_id,
                    source_correction_id=source_mutation_id,
                )
                for portfolio_id, security_id, epoch in position_keys
            ],
            rearm_completed=True,
            requeue_if_processing=True,
        )

    async def _find_open_position_keys(self, business_date: date) -> list[tuple[str, str, int]]:
        history_security_id = _normalized_security_id_expression(PositionHistory.security_id)
        state_security_id = _normalized_security_id_expression(PositionState.security_id)
        ranked_history = (
            select(
                PositionState.portfolio_id.label("portfolio_id"),
                state_security_id.label("security_id"),
                PositionState.epoch.label("epoch"),
                PositionHistory.quantity.label("quantity"),
                func.row_number()
                .over(
                    partition_by=(
                        PositionState.portfolio_id,
                        state_security_id,
                        PositionState.epoch,
                    ),
                    order_by=(
                        PositionHistory.position_date.desc(),
                        PositionHistory.id.desc(),
                    ),
                )
                .label("row_number"),
            )
            .join(
                PositionState,
                (PositionState.portfolio_id == PositionHistory.portfolio_id)
                & (state_security_id == history_security_id)
                & (PositionState.epoch == PositionHistory.epoch),
            )
            .where(PositionHistory.position_date <= business_date)
            .subquery()
        )
        rows = (
            await self.db.execute(
                select(
                    ranked_history.c.portfolio_id,
                    ranked_history.c.security_id,
                    ranked_history.c.epoch,
                )
                .where(
                    ranked_history.c.row_number == 1,
                    ranked_history.c.quantity != 0,
                )
                .order_by(
                    ranked_history.c.portfolio_id,
                    ranked_history.c.security_id,
                    ranked_history.c.epoch,
                )
            )
        ).all()
        return [(row.portfolio_id, row.security_id, row.epoch) for row in rows]
