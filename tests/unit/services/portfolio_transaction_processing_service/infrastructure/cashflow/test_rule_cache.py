"""Tests for version-aware cashflow rule caching."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import CashflowRule
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CashflowRuleCache,
    CashflowRuleSetVersion,
    SqlAlchemyCashflowRuleRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    rule_cache as rule_cache_module,
)

pytestmark = pytest.mark.asyncio


def _rule(*, timing: str = "BOD", updated_at: datetime | None = None) -> CashflowRule:
    return CashflowRule(
        transaction_type="BUY",
        classification="INVESTMENT_OUTFLOW",
        timing=timing,
        is_position_flow=True,
        is_portfolio_flow=False,
        updated_at=updated_at,
    )


async def test_concurrent_rule_requests_load_one_cache_snapshot() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = AsyncMock(spec=SqlAlchemyCashflowRuleRepository)
    repository.get_all_rules.return_value = [_rule()]
    repository.get_rule_set_version.return_value = CashflowRuleSetVersion(
        rule_count=1,
        latest_updated_at=None,
    )
    cache = CashflowRuleCache(ttl_seconds=3600)

    with patch.object(
        rule_cache_module,
        "SqlAlchemyCashflowRuleRepository",
        return_value=repository,
    ):
        first, second = await asyncio.gather(
            cache.resolve(session, "BUY"),
            cache.resolve(session, " buy "),
        )

    assert first == second
    assert first is not None
    assert repository.get_all_rules.await_count == 1


async def test_rule_cache_reloads_when_source_version_changes() -> None:
    first_version = datetime(2026, 4, 10, 8, tzinfo=timezone.utc)
    second_version = datetime(2026, 4, 10, 9, tzinfo=timezone.utc)
    repository = AsyncMock(spec=SqlAlchemyCashflowRuleRepository)
    repository.get_all_rules.side_effect = [
        [_rule(timing="BOD", updated_at=first_version)],
        [_rule(timing="EOD", updated_at=second_version)],
    ]
    repository.get_rule_set_version.side_effect = [
        CashflowRuleSetVersion(rule_count=1, latest_updated_at=second_version),
        CashflowRuleSetVersion(rule_count=1, latest_updated_at=second_version),
    ]
    cache = CashflowRuleCache(ttl_seconds=3600)

    with patch.object(
        rule_cache_module,
        "SqlAlchemyCashflowRuleRepository",
        return_value=repository,
    ):
        first = await cache.resolve(AsyncMock(spec=AsyncSession), "BUY")
        second = await cache.resolve(AsyncMock(spec=AsyncSession), "BUY")

    assert first is not None and first.timing == "BOD"
    assert second is not None and second.timing == "EOD"
    assert first.rule_set_version != second.rule_set_version
    assert second.rule_set_effective_at_utc == second_version


async def test_explicit_rule_cache_invalidation_reloads_source_snapshot() -> None:
    repository = AsyncMock(spec=SqlAlchemyCashflowRuleRepository)
    repository.get_all_rules.side_effect = [
        [_rule(timing="BOD")],
        [_rule(timing="EOD")],
    ]
    cache = CashflowRuleCache(ttl_seconds=3600)

    with patch.object(
        rule_cache_module,
        "SqlAlchemyCashflowRuleRepository",
        return_value=repository,
    ):
        first = await cache.resolve(AsyncMock(spec=AsyncSession), "BUY")
        cache.invalidate()
        second = await cache.resolve(AsyncMock(spec=AsyncSession), "BUY")

    assert first is not None and first.timing == "BOD"
    assert second is not None and second.timing == "EOD"
    assert repository.get_all_rules.await_count == 2


async def test_invalidation_during_reload_cannot_publish_invalidated_snapshot() -> None:
    first_load_started = asyncio.Event()
    permit_first_load = asyncio.Event()
    repository = AsyncMock(spec=SqlAlchemyCashflowRuleRepository)

    async def load_rules() -> list[CashflowRule]:
        if repository.get_all_rules.await_count == 1:
            first_load_started.set()
            await permit_first_load.wait()
            return [_rule(timing="BOD")]
        return [_rule(timing="EOD")]

    repository.get_all_rules.side_effect = load_rules
    cache = CashflowRuleCache(ttl_seconds=3600)

    with patch.object(
        rule_cache_module,
        "SqlAlchemyCashflowRuleRepository",
        return_value=repository,
    ):
        lookup = asyncio.create_task(cache.resolve(AsyncMock(spec=AsyncSession), "BUY"))
        await first_load_started.wait()
        cache.invalidate()
        permit_first_load.set()
        resolved = await lookup

    assert resolved is not None and resolved.timing == "EOD"
    assert repository.get_all_rules.await_count == 2
