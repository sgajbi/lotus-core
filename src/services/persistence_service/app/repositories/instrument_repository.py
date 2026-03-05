# services/persistence_service/app/repositories/instrument_repository.py
import logging

from portfolio_common.database_models import Instrument as DBInstrument
from portfolio_common.events import InstrumentEvent
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class InstrumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update_instrument(self, event: InstrumentEvent) -> DBInstrument:
        """
        Idempotently creates or updates an instrument using a native PostgreSQL UPSERT.
        """
        try:
            instrument_data = event.model_dump()

            stmt = pg_insert(DBInstrument).values(**instrument_data)

            update_dict = {
                c.name: c for c in stmt.excluded if c.name not in ["id", "security_id"]
            }

            final_stmt = stmt.on_conflict_do_update(
                index_elements=['security_id'],
                set_=update_dict
            )
            
            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for instrument '{event.security_id}'.")
            
            return DBInstrument(**instrument_data)
        except Exception as e:
            logger.error(f"Failed to stage UPSERT for instrument '{event.security_id}': {e}", exc_info=True)
            raise