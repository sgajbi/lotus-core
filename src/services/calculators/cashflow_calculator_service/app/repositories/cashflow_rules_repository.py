# src/services/calculators/cashflow_calculator_service/app/repositories/cashflow_rules_repository.py
import logging
from typing import List

from portfolio_common.database_models import CashflowRule
from portfolio_common.utils import async_timed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class CashflowRulesRepository:
    """
    Handles read-only database queries for cashflow rule data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="CashflowRulesRepository", method="get_all_rules")
    async def get_all_rules(self) -> List[CashflowRule]:
        """
        Retrieves all cashflow rules from the database.
        """
        stmt = select(CashflowRule).order_by(CashflowRule.transaction_type)
        result = await self.db.execute(stmt)
        rules = result.scalars().all()
        logger.info(f"Loaded {len(rules)} cashflow rules from the database.")
        return rules