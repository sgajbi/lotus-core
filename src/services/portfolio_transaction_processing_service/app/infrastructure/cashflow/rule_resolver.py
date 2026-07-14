"""Adapt the governed cashflow rule cache to the application resolution port."""

from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cashflow import CashflowRule
from .rule_cache import CashflowRuleCache


class CachedCashflowRuleResolver:
    """Resolve domain cashflow rules through the runtime-owned source-versioned cache."""

    def __init__(self, session: AsyncSession, cache: CashflowRuleCache) -> None:
        self._session = session
        self._cache = cache

    async def resolve(self, transaction_type: str) -> CashflowRule | None:
        cached_rule = await self._cache.resolve(self._session, transaction_type)
        if cached_rule is None:
            return None
        return CashflowRule(
            classification=cached_rule.classification,
            timing=cached_rule.timing,
            is_position_flow=cached_rule.is_position_flow,
            is_portfolio_flow=cached_rule.is_portfolio_flow,
        )
