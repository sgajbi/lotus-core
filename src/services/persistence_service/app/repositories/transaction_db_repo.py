# services/persistence_service/app/repositories/transaction_db_repo.py
import logging

from portfolio_common.database_models import Portfolio
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_portfolio_exists(self, portfolio_id: str) -> bool:
        """Checks if a portfolio with the given ID exists in the database."""
        stmt = select(exists().where(Portfolio.portfolio_id == portfolio_id))
        result = await self.db.execute(stmt)
        return result.scalar()

    async def create_or_update_transaction(self, event: TransactionEvent) -> DBTransaction:
        """
        Idempotently creates or updates a transaction using a native PostgreSQL
        UPSERT (INSERT ... ON CONFLICT DO UPDATE) for high performance and concurrency safety.
        """
        try:
            # Exclude event-only fields that do not map to the transactions table.
            event_dict = event.model_dump(
                exclude={"epoch", "brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees"},
                exclude_none=True,
            )
            
            # The statement to execute.
            stmt = pg_insert(DBTransaction).values(
                **event_dict
            )

            # Update only fields supplied by the event payload to avoid touching
            # unrelated columns during partial contract rollout.
            update_fields = [k for k in event_dict.keys() if k not in {"id", "transaction_id"}]
            update_dict = {field: getattr(stmt.excluded, field) for field in update_fields}

            # The final UPSERT statement with the conflict resolution.
            final_stmt = stmt.on_conflict_do_update(
                index_elements=['transaction_id'],
                set_=update_dict
            )
            
            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for transaction '{event.transaction_id}'.")
            
            # Note: Since UPSERT doesn't easily return the model, we can assume success.
            # The calling consumer logic doesn't depend on the returned object.
            return DBTransaction(**event_dict)

        except Exception as e:
            logger.error(f"Failed to stage UPSERT for transaction '{event.transaction_id}': {e}", exc_info=True)
            raise
