# services/calculators/cashflow_calculator_service/app/repositories/cashflow_repository.py
import logging

from portfolio_common.database_models import Cashflow, Portfolio, Transaction
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CashflowRepository:
    """
    Handles all database operations for the Cashflow model.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        result = await self.db.execute(
            select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id)
        )
        return result.scalar_one_or_none() is not None

    async def transaction_exists(
        self, transaction_id: str, *, portfolio_id: str | None = None
    ) -> bool:
        stmt = select(Transaction.transaction_id).where(
            Transaction.transaction_id == transaction_id
        )
        if portfolio_id is not None:
            stmt = stmt.where(Transaction.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_cashflow(self, cashflow: Cashflow) -> Cashflow | None:
        """
        Saves a new Cashflow record to the database within a managed transaction.
        """
        try:
            self.db.add(cashflow)
            await self.db.flush()
            await self.db.refresh(cashflow)
            logger.info(
                "Successfully staged cashflow record for transaction_id '%s' in epoch %s",
                cashflow.transaction_id,
                cashflow.epoch,
            )
            return cashflow
        except IntegrityError:
            logger.warning(
                "A cashflow for transaction_id '%s' in epoch %s may already exist. "
                "The transaction will be rolled back.",
                cashflow.transaction_id,
                cashflow.epoch,
            )
            raise
        except Exception as e:
            logger.error(
                "An unexpected error occurred while staging cashflow for txn "
                f"{cashflow.transaction_id}: {e}",
                exc_info=True,
            )
            raise
