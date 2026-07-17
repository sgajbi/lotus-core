"""Coordinate one booked transaction's governed cashflow effects."""

from __future__ import annotations

import logging

from ...domain import BookedTransaction
from ...domain.cashflow import CashflowCalculationContext, calculate_transaction_cashflow
from ...domain.transaction import (
    SettlementCashValidationError,
    assert_cash_entry_mode_supported,
    is_upstream_provided_cash_entry_mode,
)
from ...domain.transaction.corporate_action import (
    assert_bundle_a_corporate_action_valid,
    is_bundle_a_corporate_action,
)
from ...domain.transaction.processing_type import (
    requires_cashflow_processing,
    resolve_effective_processing_transaction_type,
)
from ...ports.cashflow import (
    CashflowCalculationObserver,
    CashflowEventStagingPort,
    CashflowPersistencePort,
    CashflowProcessingStatePort,
    CashflowRuleResolutionPort,
)
from ...ports.transaction_processing import CashflowProcessingResult
from ..errors import TransactionProcessingError, TransactionProcessingRejected
from ..settlement_cash_rejection import build_settlement_cash_rejection

logger = logging.getLogger(__name__)


class ProcessTransactionCashflowUseCase:
    """Resolve, calculate, and stage cashflow effects inside a caller-owned unit of work."""

    def __init__(
        self,
        *,
        rules: CashflowRuleResolutionPort,
        state: CashflowProcessingStatePort,
        persistence: CashflowPersistencePort,
        events: CashflowEventStagingPort,
        observer: CashflowCalculationObserver,
    ) -> None:
        self._rules = rules
        self._state = state
        self._persistence = persistence
        self._events = events
        self._observer = observer

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        event_id: str,
        correlation_id: str | None,
        traceparent: str | None,
        repair_existing: bool = False,
        calculation_context: CashflowCalculationContext = (
            CashflowCalculationContext.CURRENT_BOOKING
        ),
    ) -> CashflowProcessingResult:
        """Apply fences and stage at most one calculated cashflow."""

        if not await self._state.accepts_epoch(
            transaction,
            correlation_id=correlation_id,
            traceparent=traceparent,
        ):
            raise TransactionProcessingRejected(
                reason_code="cashflow_epoch_rejected",
                detail={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                    "epoch": transaction.epoch,
                },
                retryable=False,
            )

        if not repair_existing and not await self._state.claim_semantic_event(
            transaction,
            event_id=event_id,
            semantic_event_id=_semantic_cashflow_event_id(transaction),
            correlation_id=correlation_id,
        ):
            return CashflowProcessingResult()

        transaction_type = _validated_cashflow_transaction_type(transaction)
        if not requires_cashflow_processing(transaction):
            logger.debug(
                "Skipping cashflow creation for non-cash FX contract lifecycle event.",
                extra={
                    "transaction_id": transaction.transaction_id,
                    "transaction_type": transaction.transaction_type,
                    "effective_processing_type": transaction_type,
                    "component_type": transaction.component_type,
                    "fx_contract_id": transaction.fx_contract_id,
                },
            )
            return CashflowProcessingResult()

        rule = await self._rules.resolve(transaction_type)
        if rule is None:
            raise TransactionProcessingError(
                reason_code="cashflow_rule_missing",
                detail={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                    "transaction_type": transaction.transaction_type,
                },
                retryable=False,
            )

        try:
            calculated = calculate_transaction_cashflow(
                transaction,
                rule,
                epoch=transaction.epoch,
                calculation_context=calculation_context,
            )
        except SettlementCashValidationError as exc:
            raise build_settlement_cash_rejection(transaction, exc) from exc

        self._observer.calculated(calculated)

        stored = (
            await self._persistence.replace(calculated)
            if repair_existing
            else await self._persistence.create(calculated)
        )
        await self._events.stage_calculated_cashflow(
            stored,
            transaction,
            correlation_id=correlation_id,
        )
        return CashflowProcessingResult(cashflow_record_count=1)


def _semantic_cashflow_event_id(transaction: BookedTransaction) -> str:
    return (
        f"cashflow:{transaction.portfolio_id}:{transaction.transaction_id}:{transaction.epoch or 0}"
    )


def _validated_cashflow_transaction_type(transaction: BookedTransaction) -> str:
    transaction_type = resolve_effective_processing_transaction_type(transaction)
    if is_bundle_a_corporate_action(transaction_type):
        assert_bundle_a_corporate_action_valid(transaction)
    assert_cash_entry_mode_supported(transaction)
    _assert_linked_cash_leg_contract(transaction)
    return transaction_type


def _assert_linked_cash_leg_contract(transaction: BookedTransaction) -> None:
    has_linked_cash_leg = bool((transaction.external_cash_transaction_id or "").strip())
    if (
        transaction.cash_entry_mode is not None
        and is_upstream_provided_cash_entry_mode(transaction.cash_entry_mode)
        and not has_linked_cash_leg
    ):
        raise TransactionProcessingError(
            reason_code="cashflow_contract_invalid",
            detail={
                "portfolio_id": transaction.portfolio_id,
                "transaction_id": transaction.transaction_id,
            },
            retryable=False,
        )
