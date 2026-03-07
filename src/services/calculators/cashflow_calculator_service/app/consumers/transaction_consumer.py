# services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py
import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

from confluent_kafka import Message
from portfolio_common.config import (
    CASHFLOW_RULE_CACHE_TTL_SECONDS as DEFAULT_CASHFLOW_RULE_CACHE_TTL_SECONDS,
)
from portfolio_common.config import KAFKA_CASHFLOW_CALCULATED_TOPIC
from portfolio_common.database_models import CashflowRule
from portfolio_common.db import get_async_db_session
from portfolio_common.events import CashflowCalculatedEvent, TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.reprocessing import EpochFencer
from portfolio_common.transaction_domain import (
    assert_ca_bundle_a_transaction_valid,
    assert_portfolio_flow_cash_entry_mode_allowed,
    is_ca_bundle_a_transaction_type,
    normalize_cash_entry_mode,
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
class CashflowRuleCacheState:
    rules_by_transaction_type: Dict[str, CashflowRule]
    loaded_at_monotonic_seconds: float


# Module-level cache for cashflow rules.
_cashflow_rule_cache_state: Optional[CashflowRuleCacheState] = None


def invalidate_cashflow_rule_cache() -> None:
    """
    Explicit cache invalidation hook.

    Intended for operational use and tests where rules are updated and
    immediate refresh is required without process restart.
    """
    global _cashflow_rule_cache_state
    _cashflow_rule_cache_state = None


def _cache_is_fresh(cache_state: CashflowRuleCacheState) -> bool:
    if CASHFLOW_RULE_CACHE_TTL_SECONDS <= 0:
        return False
    age_seconds = time.monotonic() - cache_state.loaded_at_monotonic_seconds
    return age_seconds < CASHFLOW_RULE_CACHE_TTL_SECONDS


class NoCashflowRuleError(ValueError):
    """Custom exception for when a rule for a transaction type is not found."""

    pass


class LinkedCashLegError(ValueError):
    """Raised when a linked-cash-leg contract is malformed."""


ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"
LINKED_CASHFLOW_SKIP_TRANSACTION_TYPES = {"BUY", "SELL", "DIVIDEND", "INTEREST"}


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
            rules_by_transaction_type={rule.transaction_type.upper(): rule for rule in rules_list},
            loaded_at_monotonic_seconds=time.monotonic(),
        )

    async def _get_rule_for_transaction(
        self, db_session, transaction_type: str
    ) -> Optional[CashflowRule]:
        """
        Retrieves the cashflow rule for a given transaction type, using a
        lazy-loaded in-memory cache with TTL refresh and missing-rule refresh.
        """
        global _cashflow_rule_cache_state

        if _cashflow_rule_cache_state is None or not _cache_is_fresh(_cashflow_rule_cache_state):
            logger.info("Cashflow rules cache miss/stale; refreshing from database.")
            _cashflow_rule_cache_state = await self._load_cashflow_rules_cache(db_session)

        transaction_type_key = transaction_type.upper()
        rule = _cashflow_rule_cache_state.rules_by_transaction_type.get(transaction_type_key)
        if rule is not None:
            return rule

        # Force one immediate refresh when a requested rule is missing.
        # This supports near-real-time rule updates without waiting for TTL expiry.
        logger.info(
            "Cashflow rule '%s' not found in cache; forcing immediate refresh.",
            transaction_type_key,
        )
        _cashflow_rule_cache_state = await self._load_cashflow_rules_cache(db_session)
        return _cashflow_rule_cache_state.rules_by_transaction_type.get(transaction_type_key)

    async def process_message(self, msg: Message):
        await self._process_message_with_retry(msg)

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(15), before=before_log(logger, logging.INFO))
    async def _process_message_with_retry(self, msg: Message):
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        value = msg.value().decode("utf-8")
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()

        try:
            event_data = json.loads(value)
            event = TransactionEvent.model_validate(event_data)

            async for db in get_async_db_session():
                tx = await db.begin()
                try:
                    idempotency_repo = IdempotencyRepository(db)
                    cashflow_repo = CashflowRepository(db)
                    outbox_repo = OutboxRepository(db)

                    fencer = EpochFencer(db, service_name=SERVICE_NAME)
                    if not await fencer.check(event):
                        await tx.rollback()
                        return

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        await tx.rollback()
                        return

                    event_transaction_type = event.transaction_type.upper()
                    if is_ca_bundle_a_transaction_type(event_transaction_type):
                        assert_ca_bundle_a_transaction_valid(event)
                    assert_portfolio_flow_cash_entry_mode_allowed(event)
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
                    if (
                        event_transaction_type in LINKED_CASHFLOW_SKIP_TRANSACTION_TYPES
                        and has_linked_cash_leg
                    ):
                        logger.info(
                            "Skipping product-leg cashflow creation because "
                            "linked ADJUSTMENT cash leg is authoritative.",
                            extra={
                                "transaction_id": event.transaction_id,
                                "transaction_type": event_transaction_type,
                                "external_cash_transaction_id": event.external_cash_transaction_id,
                                "economic_event_id": event.economic_event_id,
                                "linked_transaction_group_id": event.linked_transaction_group_id,
                            },
                        )
                        await idempotency_repo.mark_event_processed(
                            event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                        )
                        await db.commit()
                        return

                    rule = await self._get_rule_for_transaction(db, event.transaction_type)
                    if not rule:
                        raise NoCashflowRuleError(
                            "No cashflow rule found for transaction type "
                            f"'{event.transaction_type}'. "
                            "Message will be sent to DLQ."
                        )

                    cashflow_to_save = CashflowLogic.calculate(event, rule, epoch=event.epoch)
                    saved = await cashflow_repo.create_cashflow(cashflow_to_save)

                    completion_evt = CashflowCalculatedEvent(
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

                    await outbox_repo.create_outbox_event(
                        aggregate_type="Cashflow",
                        aggregate_id=str(saved.portfolio_id),
                        event_type="CashflowCalculated",
                        topic=KAFKA_CASHFLOW_CALCULATED_TOPIC,
                        payload=completion_evt.model_dump(mode="json"),
                        correlation_id=correlation_id,
                    )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )
                    await db.commit()

                except Exception:
                    await tx.rollback()
                    raise

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
