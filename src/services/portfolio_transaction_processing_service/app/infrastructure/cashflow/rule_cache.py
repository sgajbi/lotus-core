"""Concurrency-safe cache for effective cashflow rule snapshots."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType

from portfolio_common.config import CASHFLOW_RULE_CACHE_TTL_SECONDS
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)
from portfolio_common.monitoring import observe_cashflow_rule_cache_event
from sqlalchemy.ext.asyncio import AsyncSession

from ..cashflow_rules_repository import (
    CashflowRuleSetVersion,
    SqlAlchemyCashflowRulesRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CachedCashflowRule:
    """Effective cashflow rule plus source-owned rule-set lineage."""

    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    rule_set_version: str
    rule_set_effective_at_utc: datetime | None


@dataclass(frozen=True, slots=True)
class CashflowRuleCacheState:
    """Immutable snapshot of normalized cashflow rules."""

    rules_by_transaction_type: Mapping[str, CachedCashflowRule]
    loaded_at_monotonic_seconds: float
    rule_set_version: str
    rule_set_effective_at_utc: datetime | None


class CashflowRuleCache:
    """Resolve rules from a version-checked cache owned by one application runtime."""

    def __init__(self, *, ttl_seconds: int = CASHFLOW_RULE_CACHE_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._state: CashflowRuleCacheState | None = None
        self._lock = asyncio.Lock()
        self._invalidation_generation = 0

    def invalidate(self) -> None:
        """Force the next lookup to load a fresh source snapshot."""

        self._invalidation_generation += 1
        self._state = None
        observe_cashflow_rule_cache_event("invalidate", "explicit")

    async def resolve(
        self,
        db_session: AsyncSession,
        transaction_type: str,
    ) -> CachedCashflowRule | None:
        """Return the effective rule, refreshing stale or incomplete snapshots once."""

        transaction_type_key = normalize_transaction_control_code(transaction_type)
        rule = await self._fresh_cached_rule_or_none(db_session, transaction_type_key)
        if rule is not None:
            return rule

        async with self._lock:
            self._state = await self._load_stable_snapshot(db_session)
            rule = self._state.rules_by_transaction_type.get(transaction_type_key)
            if rule is None:
                self._state = await self._reload_cache_for_missing_rule(
                    db_session,
                    transaction_type_key,
                )
                rule = self._state.rules_by_transaction_type.get(transaction_type_key)
            return rule

    async def _load_stable_snapshot(
        self,
        db_session: AsyncSession,
    ) -> CashflowRuleCacheState:
        while True:
            invalidation_generation = self._invalidation_generation
            state = await self._fresh_or_reloaded_rule_cache(db_session)
            if invalidation_generation == self._invalidation_generation:
                return state
            observe_cashflow_rule_cache_event("stale", "invalidated_during_reload")

    async def _fresh_cached_rule_or_none(
        self,
        db_session: AsyncSession,
        transaction_type_key: str,
    ) -> CachedCashflowRule | None:
        state = self._state
        if state is None:
            observe_cashflow_rule_cache_event("miss", "empty")
            return None
        if not self._is_fresh(state):
            observe_cashflow_rule_cache_event("stale", "ttl_expired")
            return None
        if not await self._source_version_matches(db_session, state):
            observe_cashflow_rule_cache_event("stale", "source_version_changed")
            return None
        rule = state.rules_by_transaction_type.get(transaction_type_key)
        if rule is None:
            observe_cashflow_rule_cache_event("missing_rule", "fresh_cache")
            return None
        observe_cashflow_rule_cache_event("hit", "fresh")
        return rule

    async def _fresh_or_reloaded_rule_cache(
        self,
        db_session: AsyncSession,
    ) -> CashflowRuleCacheState:
        state = self._state
        if (
            state is not None
            and self._is_fresh(state)
            and await self._source_version_matches(db_session, state)
        ):
            return state
        logger.info("Cashflow rules cache miss/stale; refreshing from database.")
        return await self._load(db_session)

    async def _reload_cache_for_missing_rule(
        self,
        db_session: AsyncSession,
        transaction_type_key: str,
    ) -> CashflowRuleCacheState:
        logger.info(
            "Cashflow rule '%s' not found in cache; forcing immediate refresh.",
            transaction_type_key,
        )
        observe_cashflow_rule_cache_event("missing_rule", "reload")
        return await self._load(db_session)

    async def _load(self, db_session: AsyncSession) -> CashflowRuleCacheState:
        repository = SqlAlchemyCashflowRulesRepository(db_session)
        rules = await repository.get_all_rules()
        rule_set_version = _rule_set_version(rules)
        logger.info("Loaded %s cashflow rules from repository.", len(rules))
        state = CashflowRuleCacheState(
            rules_by_transaction_type=MappingProxyType(
                {
                    normalize_transaction_control_code(rule.transaction_type): CachedCashflowRule(
                        classification=rule.classification,
                        timing=rule.timing,
                        is_position_flow=rule.is_position_flow,
                        is_portfolio_flow=rule.is_portfolio_flow,
                        rule_set_version=rule_set_version.fingerprint,
                        rule_set_effective_at_utc=rule_set_version.latest_updated_at,
                    )
                    for rule in rules
                }
            ),
            loaded_at_monotonic_seconds=time.monotonic(),
            rule_set_version=rule_set_version.fingerprint,
            rule_set_effective_at_utc=rule_set_version.latest_updated_at,
        )
        observe_cashflow_rule_cache_event("reload", "repository_load")
        return state

    async def _source_version_matches(
        self,
        db_session: AsyncSession,
        state: CashflowRuleCacheState,
    ) -> bool:
        source_version = await SqlAlchemyCashflowRulesRepository(db_session).get_rule_set_version()
        return bool(source_version.fingerprint == state.rule_set_version)

    def _is_fresh(self, state: CashflowRuleCacheState) -> bool:
        if self._ttl_seconds <= 0:
            return False
        age_seconds = time.monotonic() - state.loaded_at_monotonic_seconds
        return age_seconds < self._ttl_seconds


def _rule_set_version(rules: list[object]) -> CashflowRuleSetVersion:
    return CashflowRuleSetVersion(
        rule_count=len(rules),
        latest_updated_at=_latest_rule_timestamp(rules),
    )


def _latest_rule_timestamp(rules: list[object]) -> datetime | None:
    timestamps = [
        _utc_timestamp_or_none(getattr(rule, "updated_at", None))
        or _utc_timestamp_or_none(getattr(rule, "created_at", None))
        for rule in rules
    ]
    known_timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(known_timestamps) if known_timestamps else None


def _utc_timestamp_or_none(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
