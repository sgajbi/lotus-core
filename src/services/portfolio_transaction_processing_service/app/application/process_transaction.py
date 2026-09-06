"""Process one booked transaction and commit all derived financial effects atomically."""

from __future__ import annotations

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..domain import (
    BookedTransaction,
    build_transaction_correction_identity,
    build_transaction_semantic_identity,
)
from ..domain.cashflow import CashflowCalculationContext
from ..domain.transaction import (
    ORDINARY_SETTLEMENT_TRANSACTION_TYPES,
    SettlementCashValidationError,
    calculate_settlement_cash_movement,
)
from ..ports import (
    PositionProcessingResult,
    TransactionIdempotencyOutcome,
    TransactionProcessingObservation,
    TransactionProcessingObserver,
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
    TransactionProcessingUnitOfWorkFactory,
)
from .commands import ProcessTransactionCommand, TransactionProcessingIntent
from .errors import TransactionProcessingRejected
from .results import ProcessTransactionResult, TransactionProcessingStatus
from .settlement_cash_rejection import build_settlement_cash_rejection


def _financial_effect_transactions(
    processed_transactions: tuple[BookedTransaction, ...],
    position_results: list[PositionProcessingResult],
) -> tuple[BookedTransaction, ...]:
    rebuilt_transactions = _rebuilt_position_transactions(position_results)
    if not rebuilt_transactions:
        return processed_transactions

    rebuilt_transaction_keys = {
        (transaction.portfolio_id, transaction.transaction_id)
        for transaction in rebuilt_transactions
    }
    candidates = rebuilt_transactions + tuple(
        transaction
        for transaction in processed_transactions
        if (transaction.portfolio_id, transaction.transaction_id) not in rebuilt_transaction_keys
    )
    seen: set[tuple[str, str, int]] = set()
    unique_transactions = []
    for transaction in candidates:
        key = (
            transaction.portfolio_id,
            transaction.transaction_id,
            transaction.epoch or 0,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_transactions.append(transaction)
    return tuple(unique_transactions)


def _rebuilt_position_transactions(
    position_results: list[PositionProcessingResult],
) -> tuple[BookedTransaction, ...]:
    return tuple(
        transaction
        for position_result in position_results
        for transaction in position_result.cashflow_rebuild_transactions
    )


def _validate_ordinary_settlement_cash(transaction: BookedTransaction) -> None:
    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    if transaction_type not in ORDINARY_SETTLEMENT_TRANSACTION_TYPES:
        return
    try:
        calculate_settlement_cash_movement(transaction)
    except SettlementCashValidationError as exc:
        raise build_settlement_cash_rejection(transaction, exc) from exc


def _validate_lot_position_quantity_parity(
    transaction: BookedTransaction,
    position_result: PositionProcessingResult,
) -> None:
    restatement = transaction.lot_restatement
    if restatement is None:
        return
    expected_quantity = restatement.get("quantity_after")
    observed_quantity = position_result.processed_transaction_quantity
    # A coalesced/missing transaction record has no like-for-like authority and fails closed.
    if expected_quantity == observed_quantity:
        return
    raise TransactionProcessingRejected(
        reason_code="lot_quantity_vs_position_mismatch",
        detail={
            "portfolio_id": transaction.portfolio_id,
            "security_id": transaction.security_id,
            "transaction_id": transaction.transaction_id,
            "epoch": transaction.epoch or 0,
            "expected_lot_quantity": str(expected_quantity),
            "observed_position_quantity": (
                str(observed_quantity) if observed_quantity is not None else None
            ),
        },
        retryable=False,
    )


class ProcessTransactionUseCase:
    def __init__(
        self,
        unit_of_work_factory: TransactionProcessingUnitOfWorkFactory,
        observer: TransactionProcessingObserver,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._observer = observer

    async def execute(self, command: ProcessTransactionCommand) -> ProcessTransactionResult:
        with self._observer.observe(
            TransactionProcessingOperation.TRANSACTION
        ) as transaction_observation:
            try:
                result = await self._execute(command, transaction_observation)
            except TransactionProcessingRejected:
                transaction_observation.set_outcome(TransactionProcessingOutcome.REJECTED)
                raise
            transaction_observation.set_outcome(TransactionProcessingOutcome(result.status.value))
            return result

    async def _execute(
        self,
        command: ProcessTransactionCommand,
        transaction_observation: TransactionProcessingObservation,
    ) -> ProcessTransactionResult:
        transaction = command.transaction
        metadata = command.metadata
        async with self._unit_of_work_factory() as unit_of_work:
            identity = build_transaction_semantic_identity(transaction)
            with self._observer.observe(
                TransactionProcessingOperation.IDEMPOTENCY
            ) as idempotency_observation:
                idempotency_outcome = await unit_of_work.idempotency.claim(
                    tenant_id=transaction.tenant_id or "",
                    event_id=metadata.event_id,
                    portfolio_id=transaction.portfolio_id,
                    semantic_key=identity.semantic_key,
                    payload_fingerprint=identity.payload_fingerprint,
                    correlation_id=metadata.correlation_id,
                )
                correction_claimed = False
                if (
                    idempotency_outcome is TransactionIdempotencyOutcome.SEMANTIC_CONFLICT
                    and metadata.processing_intent is TransactionProcessingIntent.REPAIR
                ):
                    identity = build_transaction_correction_identity(transaction)
                    idempotency_outcome = await unit_of_work.idempotency.claim(
                        tenant_id=transaction.tenant_id or "",
                        event_id=metadata.event_id,
                        portfolio_id=transaction.portfolio_id,
                        semantic_key=identity.semantic_key,
                        payload_fingerprint=identity.payload_fingerprint,
                        correlation_id=metadata.correlation_id,
                    )
                    correction_claimed = (
                        idempotency_outcome is TransactionIdempotencyOutcome.CLAIMED
                    )
                repair_delivery_required = (
                    metadata.processing_intent is TransactionProcessingIntent.REPAIR
                    and (
                        idempotency_outcome is TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE
                        or (correction_claimed and metadata.repair_delivery_id is not None)
                    )
                )
                repair_delivery_claimed = repair_delivery_required and (
                    await unit_of_work.idempotency.claim_repair_delivery(
                        tenant_id=transaction.tenant_id or "",
                        event_id=metadata.repair_delivery_id or metadata.event_id,
                        portfolio_id=transaction.portfolio_id,
                        correlation_id=metadata.correlation_id,
                    )
                )
                repair_delivery_rejected = repair_delivery_required and not repair_delivery_claimed
                if repair_delivery_rejected:
                    idempotency_observation.set_outcome(TransactionProcessingOutcome.DUPLICATE)
                elif correction_claimed or repair_delivery_claimed:
                    idempotency_observation.set_outcome(TransactionProcessingOutcome.REPLAYED)
                elif idempotency_outcome is not TransactionIdempotencyOutcome.CLAIMED:
                    idempotency_observation.set_outcome(
                        TransactionProcessingOutcome(idempotency_outcome.value)
                    )
            duplicate_without_repair = (
                idempotency_outcome
                in {
                    TransactionIdempotencyOutcome.PHYSICAL_DUPLICATE,
                    TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE,
                }
                and not repair_delivery_claimed
            )
            if repair_delivery_rejected or duplicate_without_repair:
                transaction_observation.set_outcome(TransactionProcessingOutcome.DUPLICATE)
                return ProcessTransactionResult(
                    status=TransactionProcessingStatus.DUPLICATE,
                    input_transaction_id=transaction.transaction_id,
                )
            if idempotency_outcome is TransactionIdempotencyOutcome.SEMANTIC_CONFLICT:
                raise TransactionProcessingRejected(
                    reason_code="transaction_semantic_conflict",
                    detail={
                        "portfolio_id": transaction.portfolio_id,
                        "transaction_id": transaction.transaction_id,
                        "epoch": transaction.epoch or 0,
                        "semantic_key": identity.semantic_key,
                        "payload_fingerprint": identity.payload_fingerprint,
                    },
                    retryable=False,
                )

            _validate_ordinary_settlement_cash(transaction)
            with self._observer.observe(TransactionProcessingOperation.COST):
                cost_result = await unit_of_work.cost.process(
                    transaction,
                    correlation_id=metadata.correlation_id,
                    traceparent=metadata.traceparent,
                    reconcile_superseded_derived=correction_claimed,
                )
            position_results = []
            locked_position_epochs: dict[tuple[str, str], int] = {}
            for processed_transaction in cost_result.processed_transactions:
                with self._observer.observe(TransactionProcessingOperation.POSITION):
                    position_result = await unit_of_work.position.process(
                        processed_transaction,
                        correlation_id=metadata.correlation_id,
                        traceparent=metadata.traceparent,
                        rebuild_existing=correction_claimed or repair_delivery_claimed,
                    )
                    position_results.append(position_result)
                    _validate_lot_position_quantity_parity(
                        processed_transaction,
                        position_result,
                    )
                    if position_result.locked_state_epoch is not None:
                        locked_position_epochs[
                            (
                                processed_transaction.portfolio_id,
                                processed_transaction.security_id,
                            )
                        ] = position_result.locked_state_epoch
            rebuilt_transactions = _rebuilt_position_transactions(position_results)
            financial_effect_transactions = _financial_effect_transactions(
                cost_result.processed_transactions,
                position_results,
            )
            cashflow_results = []
            current_transaction_keys = {
                (
                    processed_transaction.portfolio_id,
                    processed_transaction.transaction_id,
                )
                for processed_transaction in cost_result.processed_transactions
            }
            historical_rebuild_cashflow_keys = {
                (
                    rebuilt_transaction.portfolio_id,
                    rebuilt_transaction.transaction_id,
                    rebuilt_transaction.epoch or 0,
                )
                for rebuilt_transaction in rebuilt_transactions
                if (
                    rebuilt_transaction.portfolio_id,
                    rebuilt_transaction.transaction_id,
                )
                not in current_transaction_keys
            }
            for cashflow_transaction in financial_effect_transactions:
                with self._observer.observe(TransactionProcessingOperation.CASHFLOW):
                    cashflow_results.append(
                        await unit_of_work.cashflow.process(
                            cashflow_transaction,
                            event_id=metadata.event_id,
                            correlation_id=metadata.correlation_id,
                            traceparent=metadata.traceparent,
                            repair_existing=(
                                metadata.processing_intent is TransactionProcessingIntent.REPAIR
                            ),
                            locked_position_epoch=locked_position_epochs.get(
                                (
                                    cashflow_transaction.portfolio_id,
                                    cashflow_transaction.security_id,
                                )
                            ),
                            calculation_context=(
                                CashflowCalculationContext.HISTORICAL_REBUILD
                                if (
                                    cashflow_transaction.portfolio_id,
                                    cashflow_transaction.transaction_id,
                                    cashflow_transaction.epoch or 0,
                                )
                                in historical_rebuild_cashflow_keys
                                else CashflowCalculationContext.CURRENT_BOOKING
                            ),
                        )
                    )
            if financial_effect_transactions:
                with self._observer.observe(TransactionProcessingOperation.PIPELINE):
                    await unit_of_work.readiness.register_processed_transactions(
                        financial_effect_transactions,
                        correlation_id=metadata.correlation_id,
                        traceparent=metadata.traceparent,
                    )
            with self._observer.observe(TransactionProcessingOperation.COMMIT):
                await unit_of_work.commit()

        return ProcessTransactionResult(
            status=TransactionProcessingStatus.PROCESSED,
            input_transaction_id=transaction.transaction_id,
            processed_transaction_ids=tuple(
                item.transaction_id for item in cost_result.processed_transactions
            ),
            instrument_update_count=cost_result.instrument_update_count,
            cashflow_record_count=sum(item.cashflow_record_count for item in cashflow_results),
            position_record_count=sum(item.position_record_count for item in position_results),
            replay_queued_count=sum(item.replay_queued for item in position_results),
        )
