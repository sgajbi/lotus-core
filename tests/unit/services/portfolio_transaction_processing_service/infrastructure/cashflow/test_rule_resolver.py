"""Test the cached rule resolver application adapter."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    CachedCashflowRule,
    CachedCashflowRuleResolver,
    CashflowRuleCache,
)

pytestmark = pytest.mark.asyncio


async def test_rule_resolver_maps_cached_lineage_record_to_domain_rule() -> None:
    session = AsyncMock(spec=AsyncSession)
    cache = AsyncMock(spec=CashflowRuleCache)
    cache.resolve.return_value = CachedCashflowRule(
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        is_position_flow=True,
        is_portfolio_flow=False,
        rule_set_version="rules-v3",
        rule_set_effective_at_utc=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    rule = await CachedCashflowRuleResolver(session, cache).resolve("BUY")

    assert rule is not None
    assert rule.classification == "INVESTMENT_OUTFLOW"
    assert rule.timing == "BOD"
    assert rule.is_position_flow is True
    assert rule.is_portfolio_flow is False
    cache.resolve.assert_awaited_once_with(session, "BUY")


async def test_rule_resolver_preserves_missing_rule() -> None:
    session = AsyncMock(spec=AsyncSession)
    cache = AsyncMock(spec=CashflowRuleCache)
    cache.resolve.return_value = None

    assert await CachedCashflowRuleResolver(session, cache).resolve("UNKNOWN") is None
