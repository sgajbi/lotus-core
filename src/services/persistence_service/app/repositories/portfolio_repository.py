# services/persistence_service/app/repositories/portfolio_repository.py
import logging

from portfolio_common.database_models import Portfolio as DBPortfolio
from portfolio_common.domain.cost_basis_method import normalize_cost_basis_method
from portfolio_common.events import PortfolioEvent
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.event_record_mapper import event_business_record_values

logger = logging.getLogger(__name__)


class PortfolioRepository:
    """
    Handles database operations for the Portfolio model.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update_portfolio(self, event: PortfolioEvent) -> DBPortfolio:
        """
        Idempotently creates or updates a portfolio using a native PostgreSQL
        UPSERT (INSERT ... ON CONFLICT DO UPDATE).
        """
        try:
            portfolio_data = event_business_record_values(event)
            portfolio_data["cost_basis_method"] = normalize_cost_basis_method(
                portfolio_data.get("cost_basis_method")
            ).value

            stmt = pg_insert(DBPortfolio).values(**portfolio_data)

            protected_update_fields = {"id", "portfolio_id"}
            if event.tenant_id is None and event.legal_book_id is None:
                protected_update_fields.update({"tenant_id", "legal_book_id"})
            update_dict = {
                column.name: column
                for column in stmt.excluded
                if column.name not in protected_update_fields
            }

            final_stmt = stmt.on_conflict_do_update(
                index_elements=["portfolio_id"], set_=update_dict
            )

            await self.db.execute(final_stmt)
            logger.debug(
                "Staged portfolio upsert.",
                extra={"portfolio_id": event.portfolio_id},
            )

            return DBPortfolio(**portfolio_data)
        except Exception:
            logger.error(
                "Failed to stage portfolio upsert.",
                extra={"portfolio_id": event.portfolio_id},
                exc_info=True,
            )
            raise
