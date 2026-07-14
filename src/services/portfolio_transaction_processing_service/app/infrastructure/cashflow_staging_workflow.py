import logging
from dataclasses import dataclass
from enum import Enum

from portfolio_common.config import (
    KAFKA_CASHFLOWS_CALCULATED_TOPIC,
)
from portfolio_common.events import CashflowCalculatedEvent, TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.reprocessing import EpochFencer
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain import BookedTransaction
from ..domain.cashflow import CashflowCalculationContext, StoredCashflow
from ..domain.transaction import (
    assert_cash_entry_mode_supported,
    is_upstream_provided_cash_entry_mode,
    requires_cashflow_processing,
    resolve_effective_processing_transaction_type,
)
from ..domain.transaction.corporate_action import (
    assert_bundle_a_corporate_action_valid,
    is_bundle_a_corporate_action,
)
from .booked_transaction_event_mapper import to_booked_transaction
from .cashflow.persistence import SqlAlchemyCashflowRepository
from .cashflow.rule_cache import CachedCashflowRule, CashflowRuleCache
from .cashflow_calculation import calculate_observed_transaction_cashflow

logger = logging.getLogger(__name__)

SERVICE_NAME = "cashflow-calculator"


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


def _validated_cashflow_transaction_type(
    event: TransactionEvent,
    booked_transaction: BookedTransaction,
) -> str:
    event_transaction_type = resolve_effective_processing_transaction_type(event)
    if is_bundle_a_corporate_action(event_transaction_type):
        assert_bundle_a_corporate_action_valid(booked_transaction)
    assert_cash_entry_mode_supported(booked_transaction)
    _assert_linked_cash_leg_contract(booked_transaction)
    return str(event_transaction_type)


def _assert_linked_cash_leg_contract(transaction: BookedTransaction) -> None:
    has_linked_cash_leg = bool((transaction.external_cash_transaction_id or "").strip())
    if (
        transaction.cash_entry_mode is not None
        and is_upstream_provided_cash_entry_mode(transaction.cash_entry_mode)
        and not has_linked_cash_leg
    ):
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
    cashflow_repo: SqlAlchemyCashflowRepository,
    outbox_repo: OutboxRepository,
    event: TransactionEvent,
    booked_transaction: BookedTransaction,
    rule: CachedCashflowRule,
    correlation_id: str,
    repair_existing: bool,
    calculation_context: CashflowCalculationContext = (CashflowCalculationContext.CURRENT_BOOKING),
) -> int:
    cashflow_to_save = calculate_observed_transaction_cashflow(
        booked_transaction,
        rule,
        epoch=event.epoch,
        calculation_context=calculation_context,
    )
    saved = (
        await cashflow_repo.replace(cashflow_to_save)
        if repair_existing
        else await cashflow_repo.create(cashflow_to_save)
    )
    completion_evt = cashflow_calculated_event_from_stored_cashflow(saved, event)
    await outbox_repo.create_outbox_event(
        aggregate_type="Cashflow",
        aggregate_id=str(saved.portfolio_id),
        event_type="CashflowCalculated",
        topic=KAFKA_CASHFLOWS_CALCULATED_TOPIC,
        payload=completion_evt.model_dump(mode="json"),
        correlation_id=correlation_id,
    )
    return 1


def cashflow_calculated_event_from_stored_cashflow(
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

    def __init__(self, rule_cache: CashflowRuleCache | None = None) -> None:
        self._rule_cache = rule_cache or CashflowRuleCache()

    def invalidate_rule_cache(self) -> None:
        """Force the next cashflow rule lookup to load a current snapshot."""

        self._rule_cache.invalidate()

    async def _get_rule_for_transaction(
        self,
        db_session: AsyncSession,
        transaction_type: str,
    ) -> CachedCashflowRule | None:
        return await self._rule_cache.resolve(db_session, transaction_type)

    async def stage_valid_event(
        self,
        *,
        db: AsyncSession,
        cashflow_repo: SqlAlchemyCashflowRepository,
        idempotency_repo: IdempotencyRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
        topic: str,
        repair_existing: bool = False,
        booked_transaction: BookedTransaction | None = None,
        calculation_context: CashflowCalculationContext = (
            CashflowCalculationContext.CURRENT_BOOKING
        ),
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
            booked_transaction=booked_transaction,
            calculation_context=calculation_context,
        )

    async def _fence_or_semantic_duplicate_outcome(
        self,
        *,
        db: AsyncSession,
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
        db: AsyncSession,
        cashflow_repo: SqlAlchemyCashflowRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        correlation_id: str,
        repair_existing: bool = False,
        booked_transaction: BookedTransaction | None = None,
        calculation_context: CashflowCalculationContext = (
            CashflowCalculationContext.CURRENT_BOOKING
        ),
    ) -> CashflowStageResult:
        booked_transaction = booked_transaction or to_booked_transaction(event)
        event_transaction_type = _validated_cashflow_transaction_type(event, booked_transaction)
        if _is_non_cashflow_lifecycle_event(event, event_transaction_type):
            return CashflowStageResult(
                outcome=CashflowProcessingOutcome.NON_CASHFLOW_LIFECYCLE_EVENT
            )
        rule = await self._required_rule_for_transaction(db, event_transaction_type)
        cashflow_record_count = await _stage_cashflow_calculation(
            cashflow_repo,
            outbox_repo,
            event,
            booked_transaction,
            rule,
            correlation_id,
            repair_existing,
            calculation_context,
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
        db: AsyncSession,
        event_transaction_type: str,
    ) -> CachedCashflowRule:
        rule = await self._get_rule_for_transaction(db, event_transaction_type)
        if rule:
            return rule
        raise NoCashflowRuleError(
            "No cashflow rule found for transaction type "
            f"'{event_transaction_type}'. Message will be sent to DLQ."
        )
