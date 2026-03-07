# src/services/calculators/position_valuation_calculator/app/repositories/
# instrument_reprocessing_state_repository.py
import logging
from datetime import date

from portfolio_common.database_models import InstrumentReprocessingState
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class InstrumentReprocessingStateRepository:
    """
    Handles database operations for the InstrumentReprocessingState model.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_state(self, security_id: str, price_date: date) -> None:
        """
        Idempotently creates or updates an instrument reprocessing state.

        If a record for the security_id already exists, it updates the
        earliest_impacted_date only if the new price_date is older.
        This ensures the watermark is always reset to the earliest required date.
        """
        try:
            stmt = pg_insert(InstrumentReprocessingState).values(
                security_id=security_id, earliest_impacted_date=price_date
            )

            # The LEAST function is specific to PostgreSQL.
            # Using text() is a reliable way to execute this database-specific function.
            update_stmt = stmt.on_conflict_do_update(
                index_elements=["security_id"],
                set_={
                    "earliest_impacted_date": text(
                        "LEAST(instrument_reprocessing_state.earliest_impacted_date, "
                        f"'{price_date.isoformat()}')"
                    ),
                    "updated_at": text("now()"),
                },
            )

            await self.db.execute(update_stmt)
            logger.info(
                f"Successfully staged UPSERT for instrument reprocessing state for '{security_id}'."
            )

        except Exception as e:
            logger.error(
                "Failed to stage UPSERT for instrument reprocessing state for "
                f"'{security_id}': {e}",
                exc_info=True,
            )
            raise
