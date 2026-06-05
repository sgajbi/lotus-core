# services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

from confluent_kafka import Message
from portfolio_common.config import (
    CASHFLOW_RULE_CACHE_TTL_SECONDS as DEFAULT_CASHFLOW_RULE_CACHE_TTL_SECONDS,
)
from portfolio_common.config import (
    KAFKA_CASHFLOWS_CALCULATED_TOPIC,
    KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
)
from portfolio_common.db import get_async_db_session
from portfolio_common.events import CashflowCalculatedEvent, TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.reprocessing import EpochFencer
from portfolio_common.transaction_domain import (
    assert_ca_bundle_a_transaction_valid,
    assert_portfolio_flow_cash_entry_mode_allowed,
    is_ca_bundle_a_transaction_type,
    normalize_cash_entry_mode,
    resolve_effective_processing_transaction_type,
)
from portfolio_common.transaction_domain.control_code_normalization import (
    normalize_transaction_control_code,
)
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import before_log, retry, stop_after_attempt, wait_fixed

from ..core.cashflow_logic import CashflowLogic
from ..repositories.cashflow_repository import CashflowRepository
from ..repositories.cashflow_rules_repository import CashflowRulesRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cashflow-calculator"

CASHFLOW_RULE_CACHE_TTL_SECONDS = DEFAULT_CASHFLOW_RULE_CACHE_TTL_SECONDS


@dataclass
class CachedCashflowRule:
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool


@dataclass
class CashflowRuleCacheState:
    rules_by_transaction_type: Dict[str, CachedCashflowRule]
    loaded_at_monotonic_seconds: float


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


def _get_cashflow_rule_cache_lock() -> asyncio.Lock:
    global _cashflow_rule_cache_lock
    if _cashflow_rule_cache_lock is None:
        _cashflow_rule_cache_lock = asyncio.Lock()
    return _cashflow_rule_cache_lock


def _cache_is_fresh(cache_state: CashflowRuleCacheState) -> bool:
    if CASHFLOW_RULE_CACHE_TTL_SECONDS <= 0:
        return False
    age_seconds = time.monotonic() - cache_state.loaded_at_monotonic_seconds
    return age_seconds < CASHFLOW_RULE_CACHE_TTL_SECONDS


def _fresh_cached_rule(
    cache_state: Optional[CashflowRuleCacheState],
    transaction_type_key: str,
) -> Optional[CachedCashflowRule]:
    if cache_state is None or not _cache_is_fresh(cache_state):
        return None
    return _rule_from_cache(cache_state, transaction_type_key)


def _rule_from_cache(
    cache_state: CashflowRuleCacheState,
    transaction_type_key: str,
) -> Optional[CachedCashflowRule]:
    return cache_state.rules_by_transaction_type.get(transaction_type_key)


class NoCashflowRuleError(ValueError):
    """Custom exception for when a rule for a transaction type is not found."""

    pass


class LinkedCashLegError(ValueError):
    """Raised when a linked-cash-leg contract is malformed."""


ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"
NON_CASHFLOW_EFFECTIVE_PROCESSING_TYPES = {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"}


def _semantic_cashflow_event_id(event: TransactionEvent) -> str:
    return f"cashflow:{event.portfolio_id}:{event.transaction_id}:{event.epoch or 0}"


def _validated_cashflow_transaction_type(event: TransactionEvent) -> str:
    event_transaction_type = resolve_effective_processing_transaction_type(event)
    if is_ca_bundle_a_transaction_type(event_transaction_type):
        assert_ca_bundle_a_transaction_valid(event)
    assert_portfolio_flow_cash_entry_mode_allowed(event)
    _assert_linked_cash_leg_contract(event)
    return event_transaction_type


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
    if event_transaction_type not in NON_CASHFLOW_EFFECTIVE_PROCESSING_TYPES:
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
) -> None:
    cashflow_to_save = CashflowLogic.calculate(event, rule, epoch=event.epoch)
    saved = await cashflow_repo.create_cashflow(cashflow_to_save)
    completion_evt = _cashflow_calculated_event_from_saved_cashflow(saved)
    await outbox_repo.create_outbox_event(
        aggregate_type="Cashflow",
        aggregate_id=str(saved.portfolio_id),
        event_type="CashflowCalculated",
        topic=KAFKA_CASHFLOWS_CALCULATED_TOPIC,
        payload=completion_evt.model_dump(mode="json"),
        correlation_id=correlation_id,
    )


def _cashflow_calculated_event_from_saved_cashflow(saved) -> CashflowCalculatedEvent:
    return CashflowCalculatedEvent(
        cashflow_id=saved.id,
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
    )


class CashflowCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction completion events, calculates the corresponding
    cashflow based on rules from the database, persists it, and writes a
    completion event to the outbox.
    """

    async def _load_cashflow_rules_cache(self, db_session) -> CashflowRuleCacheState:
        repo = CashflowRulesRepository(db_session)
        rules_list = await repo.get_all_rules()
        logger.info("Loaded %s cashflow rules from repository.", len(rules_list))
        return CashflowRuleCacheState(
            rules_by_transaction_type={
                normalize_transaction_control_code(rule.transaction_type): CachedCashflowRule(
                    classification=rule.classification,
                    timing=rule.timing,
                    is_position_flow=rule.is_position_flow,
                    is_portfolio_flow=rule.is_portfolio_flow,
                )
                for rule in rules_list
            },
            loaded_at_monotonic_seconds=time.monotonic(),
        )

    async def _get_rule_for_transaction(
        self, db_session, transaction_type: str
    ) -> Optional[CachedCashflowRule]:
        """
        Retrieves the cashflow rule for a given transaction type, using a
        lazy-loaded in-memory cache with TTL refresh and missing-rule refresh.
        """
        global _cashflow_rule_cache_state

        transaction_type_key = normalize_transaction_control_code(transaction_type)
        rule = _fresh_cached_rule(_cashflow_rule_cache_state, transaction_type_key)
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

    async def _fresh_or_reloaded_rule_cache(self, db_session) -> CashflowRuleCacheState:
        cache_state = _cashflow_rule_cache_state
        if cache_state is not None and _cache_is_fresh(cache_state):
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
        return await self._load_cashflow_rules_cache(db_session)

    async def process_message(self, msg: Message):
        await self._process_message_with_retry(msg)

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(15), before=before_log(logger, logging.INFO))
    async def _process_message_with_retry(self, msg: Message):
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        value = msg.value().decode("utf-8")
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

        try:
            event_data = json.loads(value)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = TransactionEvent.model_validate(event_data)
                semantic_event_id = _semantic_cashflow_event_id(event)

                async for db in get_async_db_session():
                    await self._process_validated_cashflow_event(
                        db,
                        msg,
                        event,
                        event_id,
                        semantic_event_id,
                        correlation_id,
                    )

        except (json.JSONDecodeError, ValidationError):
            logger.error("Message validation failed. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid cashflow event payload"))
        except IntegrityError:
            logger.warning("DB integrity error; will retry...", exc_info=False)
            raise
        except NoCashflowRuleError as e:
            logger.error(
                f"Configuration error: {e}. This is a non-retryable error. Sending to DLQ."
            )
            await self._send_to_dlq_async(msg, e)
        except LinkedCashLegError as e:
            logger.error(f"Linked cash-leg contract error: {e}. Sending to DLQ.")
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(
                f"Unexpected error processing message with key '{key}'. Sending to DLQ.",
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, e)

    async def _process_validated_cashflow_event(
        self,
        db,
        msg: Message,
        event: TransactionEvent,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str,
    ) -> None:
        tx = await db.begin()
        try:
            idempotency_repo = IdempotencyRepository(db)
            cashflow_repo = CashflowRepository(db)
            outbox_repo = OutboxRepository(db)

            if await self._stop_after_physical_or_stale_replay(
                db,
                tx,
                cashflow_repo,
                idempotency_repo,
                event,
                event_id,
                correlation_id,
                msg.topic(),
            ):
                return

            if await self._stop_after_fence_or_semantic_duplicate(
                db,
                tx,
                idempotency_repo,
                event,
                event_id,
                semantic_event_id,
                correlation_id,
                msg.topic(),
            ):
                return

            await self._stage_or_skip_cashflow_calculation(
                db,
                cashflow_repo,
                outbox_repo,
                event,
                correlation_id,
            )
        except Exception:
            await tx.rollback()
            raise

    async def _stop_after_physical_or_stale_replay(
        self,
        db,
        tx,
        cashflow_repo: CashflowRepository,
        idempotency_repo: IdempotencyRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
        topic: str,
    ) -> bool:
        if not await self._claim_physical_event(
            idempotency_repo,
            event,
            event_id,
            correlation_id,
        ):
            await tx.rollback()
            return True
        if await self._should_skip_stale_replay_event(cashflow_repo, event, topic):
            await db.commit()
            return True
        return False

    async def _stop_after_fence_or_semantic_duplicate(
        self,
        db,
        tx,
        idempotency_repo: IdempotencyRepository,
        event: TransactionEvent,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str,
        topic: str,
    ) -> bool:
        fencer = EpochFencer(db, service_name=SERVICE_NAME)
        if not await fencer.check(event):
            await tx.rollback()
            return True
        if not await self._claim_semantic_event(
            idempotency_repo,
            event,
            event_id,
            semantic_event_id,
            correlation_id,
            topic,
        ):
            await db.commit()
            return True
        return False

    async def _stage_or_skip_cashflow_calculation(
        self,
        db,
        cashflow_repo: CashflowRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        correlation_id: str,
    ) -> None:
        event_transaction_type = _validated_cashflow_transaction_type(event)
        if _is_non_cashflow_lifecycle_event(event, event_transaction_type):
            await db.commit()
            return
        rule = await self._required_rule_for_transaction(db, event_transaction_type)
        await _stage_cashflow_calculation(
            cashflow_repo,
            outbox_repo,
            event,
            rule,
            correlation_id,
        )
        await db.commit()

    async def _claim_physical_event(
        self,
        idempotency_repo: IdempotencyRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
    ) -> bool:
        claimed = await idempotency_repo.claim_event_processing(
            event_id,
            event.portfolio_id,
            SERVICE_NAME,
            correlation_id,
        )
        if not claimed:
            logger.warning(f"Event {event_id} already processed. Skipping.")
        return claimed

    async def _should_skip_stale_replay_event(
        self,
        cashflow_repo: CashflowRepository,
        event: TransactionEvent,
        topic: str,
    ) -> bool:
        if topic != KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC:
            return False
        portfolio_exists = await cashflow_repo.portfolio_exists(event.portfolio_id)
        transaction_exists = await cashflow_repo.transaction_exists(
            event.transaction_id,
            portfolio_id=event.portfolio_id,
        )
        if portfolio_exists and transaction_exists:
            return False
        _log_stale_replay_cashflow_skip(event, topic, portfolio_exists, transaction_exists)
        return True

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
        return claimed

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
