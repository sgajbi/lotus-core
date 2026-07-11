import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from portfolio_common.config import (
    CASHFLOW_RULE_CACHE_TTL_SECONDS as DEFAULT_CASHFLOW_RULE_CACHE_TTL_SECONDS,
)
from portfolio_common.config import (
    KAFKA_CASHFLOWS_CALCULATED_TOPIC,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)
from portfolio_common.events import CashflowCalculatedEvent, TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.monitoring import observe_cashflow_rule_cache_event
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.reprocessing import EpochFencer
from portfolio_common.transaction_domain import (
    assert_ca_bundle_a_transaction_valid,
    assert_portfolio_flow_cash_entry_mode_allowed,
    is_ca_bundle_a_transaction_type,
    normalize_cash_entry_mode,
    requires_cashflow_processing,
    resolve_effective_processing_transaction_type,
)

from .core.cashflow_logic import CashflowLogic
from .core.stored_cashflow import StoredCashflow
from .repositories.cashflow_repository import CashflowRepository
from .repositories.cashflow_rules_repository import CashflowRuleSetVersion, CashflowRulesRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cashflow-calculator"

CASHFLOW_RULE_CACHE_TTL_SECONDS = DEFAULT_CASHFLOW_RULE_CACHE_TTL_SECONDS


@dataclass
class CachedCashflowRule:
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    rule_set_version: str
    rule_set_effective_at_utc: datetime | None


@dataclass
class CashflowRuleCacheState:
    rules_by_transaction_type: Dict[str, CachedCashflowRule]
    loaded_at_monotonic_seconds: float
    rule_set_version: str
    rule_set_effective_at_utc: datetime | None


# Module-level cache for cashflow rules.
_cashflow_rule_cache_state: Optional[CashflowRuleCacheState] = None
_cashflow_rule_cache_lock: Optional[asyncio.Lock] = None


def invalidate_cashflow_rule_cache() -> None:
    """
    Explicit cache invalidation hook.

    Intended for operational use and tests where rules are updated and
    immediate refresh is required without process restart.
    """
    global _cashflow_rule_cache_state
    _cashflow_rule_cache_state = None
    observe_cashflow_rule_cache_event("invalidate", "explicit")


def _get_cashflow_rule_cache_lock() -> asyncio.Lock:
    global _cashflow_rule_cache_lock
    if _cashflow_rule_cache_lock is None:
        _cashflow_rule_cache_lock = asyncio.Lock()
    return _cashflow_rule_cache_lock


def _cache_is_fresh(cache_state: CashflowRuleCacheState) -> bool:
    if CASHFLOW_RULE_CACHE_TTL_SECONDS <= 0:
        return False
    age_seconds = time.monotonic() - cache_state.loaded_at_monotonic_seconds
    return bool(age_seconds < CASHFLOW_RULE_CACHE_TTL_SECONDS)


def _rule_from_cache(
    cache_state: CashflowRuleCacheState,
    transaction_type_key: str,
) -> Optional[CachedCashflowRule]:
    return cache_state.rules_by_transaction_type.get(transaction_type_key)


def _cashflow_rule_set_version_from_rules(rules_list: list[object]) -> CashflowRuleSetVersion:
    latest_updated_at = _latest_cashflow_rule_updated_at(rules_list)
    return CashflowRuleSetVersion(
        rule_count=len(rules_list),
        latest_updated_at=latest_updated_at,
    )


def _latest_cashflow_rule_updated_at(rules_list: list[object]) -> datetime | None:
    timestamps = [
        _utc_timestamp_or_none(getattr(rule, "updated_at", None))
        or _utc_timestamp_or_none(getattr(rule, "created_at", None))
        for rule in rules_list
    ]
    known_timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    if not known_timestamps:
        return None
    return max(known_timestamps)


def _utc_timestamp_or_none(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class NoCashflowRuleError(ValueError):
    """Custom exception for when a rule for a transaction type is not found."""

    pass


class LinkedCashLegError(ValueError):
    """Raised when a linked-cash-leg contract is malformed."""


class CashflowProcessingOutcome(str, Enum):
    PROCESSED = "processed"
    PHYSICAL_DUPLICATE = "physical_duplicate"
    STALE_REPLAY_SKIPPED = "stale_replay_skipped"
    EPOCH_REJECTED = "epoch_rejected"
    SEMANTIC_DUPLICATE = "semantic_duplicate"
    NON_CASHFLOW_LIFECYCLE_EVENT = "non_cashflow_lifecycle_event"


@dataclass(frozen=True)
class CashflowStageResult:
    outcome: CashflowProcessingOutcome
    cashflow_record_count: int = 0


ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"
CASHFLOW_COMMIT_OUTCOMES = {
    CashflowProcessingOutcome.PROCESSED,
    CashflowProcessingOutcome.STALE_REPLAY_SKIPPED,
    CashflowProcessingOutcome.SEMANTIC_DUPLICATE,
    CashflowProcessingOutcome.NON_CASHFLOW_LIFECYCLE_EVENT,
}


def _semantic_cashflow_event_id(event: TransactionEvent) -> str:
    return f"cashflow:{event.portfolio_id}:{event.transaction_id}:{event.epoch or 0}"


def _validated_cashflow_transaction_type(event: TransactionEvent) -> str:
    event_transaction_type = resolve_effective_processing_transaction_type(event)
    if is_ca_bundle_a_transaction_type(event_transaction_type):
        assert_ca_bundle_a_transaction_valid(event)
    assert_portfolio_flow_cash_entry_mode_allowed(event)
    _assert_linked_cash_leg_contract(event)
    return str(event_transaction_type)


def _assert_linked_cash_leg_contract(event: TransactionEvent) -> None:
    normalized_mode = (
        normalize_cash_entry_mode(event.cash_entry_mode)
        if event.cash_entry_mode is not None
        else None
    )
    has_linked_cash_leg = bool((event.external_cash_transaction_id or "").strip())
    if normalized_mode == "UPSTREAM_PROVIDED" and not has_linked_cash_leg:
        raise LinkedCashLegError(
            "UPSTREAM_PROVIDED product leg requires external_cash_transaction_id."
        )


def _is_non_cashflow_lifecycle_event(
    event: TransactionEvent,
    event_transaction_type: str,
) -> bool:
    if requires_cashflow_processing(event):
        return False
    logger.info(
        "Skipping cashflow creation for non-cash FX contract lifecycle event.",
        extra={
            "transaction_id": event.transaction_id,
            "transaction_type": event.transaction_type,
            "effective_processing_type": event_transaction_type,
            "component_type": event.component_type,
            "fx_contract_id": event.fx_contract_id,
        },
    )
    return True


def _log_stale_replay_cashflow_skip(
    event: TransactionEvent,
    topic: str,
    portfolio_exists: bool,
    transaction_exists: bool,
) -> None:
    logger.warning(
        "Skipping stale replay cashflow event because canonical state has already been removed.",
        extra={
            "transaction_id": event.transaction_id,
            "portfolio_id": event.portfolio_id,
            "security_id": event.security_id,
            "epoch": event.epoch or 0,
            "portfolio_exists": portfolio_exists,
            "transaction_exists": transaction_exists,
            "topic": topic,
        },
    )


def _log_semantic_cashflow_duplicate(
    event: TransactionEvent,
    event_id: str,
    semantic_event_id: str,
    topic: str,
) -> None:
    logger.info(
        "Semantic cashflow event already processed. Skipping duplicate cross-topic publication.",
        extra={
            "transaction_id": event.transaction_id,
            "portfolio_id": event.portfolio_id,
            "epoch": event.epoch or 0,
            "event_id": event_id,
            "semantic_event_id": semantic_event_id,
            "topic": topic,
        },
    )


async def _stage_cashflow_calculation(
    cashflow_repo: CashflowRepository,
    outbox_repo: OutboxRepository,
    event: TransactionEvent,
    rule: CachedCashflowRule,
    correlation_id: str,
    repair_existing: bool,
) -> int:
    cashflow_to_save = CashflowLogic.calculate(event, rule, epoch=event.epoch)
    saved = (
        await cashflow_repo.replace_cashflow(cashflow_to_save)
        if repair_existing
        else await cashflow_repo.create_cashflow(cashflow_to_save)
    )
    completion_evt = _cashflow_calculated_event_from_saved_cashflow(saved, event)
    await outbox_repo.create_outbox_event(
        aggregate_type="Cashflow",
        aggregate_id=str(saved.portfolio_id),
        event_type="CashflowCalculated",
        topic=KAFKA_CASHFLOWS_CALCULATED_TOPIC,
        payload=completion_evt.model_dump(mode="json"),
        correlation_id=correlation_id,
    )
    return 1


def _cashflow_calculated_event_from_saved_cashflow(
    saved: StoredCashflow,
    source_event: TransactionEvent,
) -> CashflowCalculatedEvent:
    return CashflowCalculatedEvent(
        cashflow_id=saved.cashflow_id,
        transaction_id=saved.transaction_id,
        portfolio_id=saved.portfolio_id,
        security_id=saved.security_id,
        cashflow_date=saved.cashflow_date,
        amount=saved.amount,
        currency=saved.currency,
        classification=saved.classification,
        timing=saved.timing,
        is_position_flow=saved.is_position_flow,
        is_portfolio_flow=saved.is_portfolio_flow,
        calculation_type=saved.calculation_type,
        epoch=saved.epoch,
        economic_event_id=saved.economic_event_id,
        linked_transaction_group_id=saved.linked_transaction_group_id,
        parent_event_reference=source_event.parent_event_reference,
        linked_cash_transaction_id=source_event.linked_cash_transaction_id,
    )


class CashflowCalculationWorkflow:
    """
    Resolve governed cashflow rules and stage cashflow plus compatibility outbox effects.

    Database transaction, physical message idempotency, retry, and delivery lifecycle ownership
    remain outside this workflow.
    """

    async def _load_cashflow_rules_cache(self, db_session) -> CashflowRuleCacheState:
        repo = CashflowRulesRepository(db_session)
        rules_list = await repo.get_all_rules()
        rule_set_version = _cashflow_rule_set_version_from_rules(rules_list)
        logger.info("Loaded %s cashflow rules from repository.", len(rules_list))
        cache_state = CashflowRuleCacheState(
            rules_by_transaction_type={
                normalize_transaction_control_code(rule.transaction_type): CachedCashflowRule(
                    classification=rule.classification,
                    timing=rule.timing,
                    is_position_flow=rule.is_position_flow,
                    is_portfolio_flow=rule.is_portfolio_flow,
                    rule_set_version=rule_set_version.fingerprint,
                    rule_set_effective_at_utc=rule_set_version.latest_updated_at,
                )
                for rule in rules_list
            },
            loaded_at_monotonic_seconds=time.monotonic(),
            rule_set_version=rule_set_version.fingerprint,
            rule_set_effective_at_utc=rule_set_version.latest_updated_at,
        )
        observe_cashflow_rule_cache_event("reload", "repository_load")
        return cache_state

    async def _get_rule_for_transaction(
        self, db_session, transaction_type: str
    ) -> Optional[CachedCashflowRule]:
        """
        Retrieves the cashflow rule for a given transaction type, using a
        lazy-loaded in-memory cache with TTL refresh and missing-rule refresh.
        """
        global _cashflow_rule_cache_state

        transaction_type_key = normalize_transaction_control_code(transaction_type)
        rule = await self._fresh_cached_rule_or_none(
            db_session,
            _cashflow_rule_cache_state,
            transaction_type_key,
        )
        if rule is not None:
            return rule

        lock = _get_cashflow_rule_cache_lock()
        async with lock:
            _cashflow_rule_cache_state = await self._fresh_or_reloaded_rule_cache(db_session)
            rule = _rule_from_cache(_cashflow_rule_cache_state, transaction_type_key)
            if rule is None:
                _cashflow_rule_cache_state = await self._reload_cache_for_missing_rule(
                    db_session,
                    transaction_type_key,
                )
                rule = _rule_from_cache(_cashflow_rule_cache_state, transaction_type_key)
            return rule

    async def _fresh_cached_rule_or_none(
        self,
        db_session,
        cache_state: Optional[CashflowRuleCacheState],
        transaction_type_key: str,
    ) -> Optional[CachedCashflowRule]:
        if cache_state is None:
            observe_cashflow_rule_cache_event("miss", "empty")
            return None
        if not _cache_is_fresh(cache_state):
            observe_cashflow_rule_cache_event("stale", "ttl_expired")
            return None
        if not await self._cache_source_version_matches(db_session, cache_state):
            observe_cashflow_rule_cache_event("stale", "source_version_changed")
            return None
        rule = _rule_from_cache(cache_state, transaction_type_key)
        if rule is None:
            observe_cashflow_rule_cache_event("missing_rule", "fresh_cache")
            return None
        observe_cashflow_rule_cache_event("hit", "fresh")
        return rule

    async def _cache_source_version_matches(
        self,
        db_session,
        cache_state: CashflowRuleCacheState,
    ) -> bool:
        repo = CashflowRulesRepository(db_session)
        source_version = await repo.get_rule_set_version()
        return bool(source_version.fingerprint == cache_state.rule_set_version)

    async def _fresh_or_reloaded_rule_cache(self, db_session) -> CashflowRuleCacheState:
        cache_state = _cashflow_rule_cache_state
        if (
            cache_state is not None
            and _cache_is_fresh(cache_state)
            and await self._cache_source_version_matches(db_session, cache_state)
        ):
            return cache_state
        logger.info("Cashflow rules cache miss/stale; refreshing from database.")
        return await self._load_cashflow_rules_cache(db_session)

    async def _reload_cache_for_missing_rule(
        self,
        db_session,
        transaction_type_key: str,
    ) -> CashflowRuleCacheState:
        # Force one immediate refresh when a requested rule is missing.
        # This supports near-real-time rule updates without waiting for TTL expiry.
        logger.info(
            "Cashflow rule '%s' not found in cache; forcing immediate refresh.",
            transaction_type_key,
        )
        observe_cashflow_rule_cache_event("missing_rule", "reload")
        return await self._load_cashflow_rules_cache(db_session)

    async def stage_valid_event(
        self,
        *,
        db,
        cashflow_repo: CashflowRepository,
        idempotency_repo: IdempotencyRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
        topic: str,
        repair_existing: bool = False,
    ) -> CashflowStageResult:
        """Stage cashflow work inside the caller-owned transaction."""
        fence_outcome = await self._fence_or_semantic_duplicate_outcome(
            db=db,
            idempotency_repo=idempotency_repo,
            event=event,
            event_id=event_id,
            semantic_event_id=_semantic_cashflow_event_id(event),
            correlation_id=correlation_id,
            topic=topic,
            repair_existing=repair_existing,
        )
        if fence_outcome is not None:
            return CashflowStageResult(outcome=fence_outcome)
        return await self._stage_cashflow_processing(
            db=db,
            cashflow_repo=cashflow_repo,
            outbox_repo=outbox_repo,
            event=event,
            correlation_id=correlation_id,
            repair_existing=repair_existing,
        )

    async def _fence_or_semantic_duplicate_outcome(
        self,
        *,
        db,
        idempotency_repo: IdempotencyRepository,
        event: TransactionEvent,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str,
        topic: str,
        repair_existing: bool = False,
    ) -> CashflowProcessingOutcome | None:
        fencer = EpochFencer(db, service_name=SERVICE_NAME)
        if not await fencer.check(event):
            return CashflowProcessingOutcome.EPOCH_REJECTED
        if repair_existing:
            return None
        if not await self._claim_semantic_event(
            idempotency_repo,
            event,
            event_id,
            semantic_event_id,
            correlation_id,
            topic,
        ):
            return CashflowProcessingOutcome.SEMANTIC_DUPLICATE
        return None

    async def _stage_cashflow_processing(
        self,
        *,
        db,
        cashflow_repo: CashflowRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        correlation_id: str,
        repair_existing: bool = False,
    ) -> CashflowStageResult:
        event_transaction_type = _validated_cashflow_transaction_type(event)
        if _is_non_cashflow_lifecycle_event(event, event_transaction_type):
            return CashflowStageResult(
                outcome=CashflowProcessingOutcome.NON_CASHFLOW_LIFECYCLE_EVENT
            )
        rule = await self._required_rule_for_transaction(db, event_transaction_type)
        cashflow_record_count = await _stage_cashflow_calculation(
            cashflow_repo,
            outbox_repo,
            event,
            rule,
            correlation_id,
            repair_existing,
        )
        return CashflowStageResult(
            outcome=CashflowProcessingOutcome.PROCESSED,
            cashflow_record_count=cashflow_record_count,
        )

    async def _claim_semantic_event(
        self,
        idempotency_repo: IdempotencyRepository,
        event: TransactionEvent,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str,
        topic: str,
    ) -> bool:
        claimed = await idempotency_repo.claim_event_processing(
            semantic_event_id,
            event.portfolio_id,
            SERVICE_NAME,
            correlation_id,
        )
        if not claimed:
            _log_semantic_cashflow_duplicate(event, event_id, semantic_event_id, topic)
        return bool(claimed)

    async def _required_rule_for_transaction(
        self,
        db,
        event_transaction_type: str,
    ) -> CachedCashflowRule:
        rule = await self._get_rule_for_transaction(db, event_transaction_type)
        if rule:
            return rule
        raise NoCashflowRuleError(
            "No cashflow rule found for transaction type "
            f"'{event_transaction_type}'. Message will be sent to DLQ."
        )
