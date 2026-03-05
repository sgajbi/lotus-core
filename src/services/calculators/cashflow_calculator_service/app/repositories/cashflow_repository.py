# services/calculators/cashflow_calculator_service/app/repositories/cashflow_repository.py
import logging

from portfolio_common.database_models import Cashflow
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CashflowRepository:
    """
    Handles all database operations for the Cashflow model.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_cashflow(self, cashflow: Cashflow) -> Cashflow | None:
        """
        Saves a new Cashflow record to the database within a managed transaction.
        """
        try:
            self.db.add(cashflow)
            await self.db.flush()
            await self.db.refresh(cashflow)
            logger.info(
                f"Successfully staged cashflow record for transaction_id: {cashflow.transaction_id}"
            )
            return cashflow
        except IntegrityError:
            logger.warning(
                f"A cashflow for transaction_id '{cashflow.transaction_id}' may already exist. "
                "The transaction will be rolled back."
            )
            raise
        except Exception as e:
            logger.error(
                "An unexpected error occurred while staging cashflow for txn "
                f"{cashflow.transaction_id}: {e}",
                exc_info=True,
            )
            raise
