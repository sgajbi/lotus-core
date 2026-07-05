# src/services/calculators/cashflow_calculator_service/app/repositories/cashflow_rules_repository.py
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from portfolio_common.database_models import CashflowRule
from portfolio_common.utils import async_timed
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CashflowRuleSetVersion:
    rule_count: int
    latest_updated_at: datetime | None

    @property
    def fingerprint(self) -> str:
        timestamp = _version_timestamp_text(self.latest_updated_at)
        return f"cashflow-rules:v1:count={self.rule_count}:latest_updated_at={timestamp}"


def _version_timestamp_text(value: datetime | None) -> str:
    if value is None:
        return "none"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


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

    @async_timed(repository="CashflowRulesRepository", method="get_rule_set_version")
    async def get_rule_set_version(self) -> CashflowRuleSetVersion:
        """
        Retrieves the source-owned version marker for cached cashflow rules.
        """
        stmt = select(
            func.count(CashflowRule.transaction_type),
            func.max(CashflowRule.updated_at),
        )
        result = await self.db.execute(stmt)
        rule_count, latest_updated_at = result.one()
        return CashflowRuleSetVersion(
            rule_count=int(rule_count or 0),
            latest_updated_at=latest_updated_at,
        )
