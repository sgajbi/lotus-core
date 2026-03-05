# src/services/persistence_service/app/repositories/business_date_repository.py
import logging

from portfolio_common.database_models import BusinessDate as DBBusinessDate
from portfolio_common.events import BusinessDateEvent
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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
            business_date_data = {"date": event.business_date}
            business_date_data["calendar_code"] = event.calendar_code
            business_date_data["market_code"] = event.market_code
            business_date_data["source_system"] = event.source_system
            business_date_data["source_batch_id"] = event.source_batch_id

            stmt = pg_insert(DBBusinessDate).values(**business_date_data)

            # If the date already exists, do nothing. This makes the operation idempotent.
            final_stmt = stmt.on_conflict_do_nothing(index_elements=["calendar_code", "date"])

            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for business date '{event.business_date}'.")

        except Exception as e:
            logger.error(
                f"Failed to stage UPSERT for business date '{event.business_date}': {e}",
                exc_info=True,
            )
            raise
