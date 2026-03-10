# services/persistence_service/app/repositories/portfolio_repository.py
import logging

from portfolio_common.cost_basis import normalize_cost_basis_method
from portfolio_common.database_models import Portfolio as DBPortfolio
from portfolio_common.events import PortfolioEvent
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

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
            portfolio_data = event.model_dump()
            portfolio_data["cost_basis_method"] = normalize_cost_basis_method(
                portfolio_data.get("cost_basis_method")
            ).value

            stmt = pg_insert(DBPortfolio).values(**portfolio_data)

            update_dict = {c.name: c for c in stmt.excluded if c.name not in ["id", "portfolio_id"]}

            final_stmt = stmt.on_conflict_do_update(
                index_elements=["portfolio_id"], set_=update_dict
            )

            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for portfolio '{event.portfolio_id}'.")

            return DBPortfolio(**portfolio_data)
        except Exception as e:
            logger.error(
                f"Failed to stage UPSERT for portfolio '{event.portfolio_id}': {e}", exc_info=True
            )
            raise
