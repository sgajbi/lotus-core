"""Process one booked transaction and commit all derived financial effects atomically."""

from __future__ import annotations

from dataclasses import replace
from typing import TypedDict

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..domain import (
    BookedTransaction,
    TransactionSemanticIdentity,
    build_transaction_correction_identity,
    build_transaction_semantic_identity,
)
from ..domain.cashflow import CashflowCalculationContext
from ..domain.transaction import (
    ORDINARY_SETTLEMENT_TRANSACTION_TYPES,
    SettlementCashValidationError,
    calculate_settlement_cash_movement,
)
from ..domain.transaction.fx import FX_BUSINESS_TRANSACTION_TYPES
from ..domain.transaction.fx.persisted_return import FxBookingContext, FxPersistenceWitness
from ..ports import (
    PositionProcessingResult,
    TransactionIdempotencyOutcome,
    TransactionIdempotencyPort,
    TransactionProcessingObservation,
    TransactionProcessingObserver,
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
    TransactionProcessingUnitOfWork,
    TransactionProcessingUnitOfWorkFactory,
)
from ..ports.position_history import AdmittedPositionCorrectionGroup
from ..ports.processing_diagnostics import diagnostic_delivery, diagnostic_phase
from ..ports.transaction_processing import FirstPublicationSourceAuthority, FxSourceAdmission
from .commands import ProcessTransactionCommand, TransactionProcessingIntent
from .errors import TransactionProcessingRejected
from .results import ProcessTransactionResult, TransactionProcessingStatus
from .settlement_cash_rejection import build_settlement_cash_rejection


class _FxBookingArguments(TypedDict, total=False):
    fx_booking_context: FxBookingContext


def _fx_booking_arguments(
    command: ProcessTransactionCommand,
    *,
    idempotency_outcome: TransactionIdempotencyOutcome,
    correction_claimed: bool,
    repair_delivery_claimed: bool,
    retention_witness: FxPersistenceWitness | None = None,
) -> _FxBookingArguments:
    transaction = command.transaction
    if (
        normalize_transaction_control_code(transaction.transaction_type)
        not in FX_BUSINESS_TRANSACTION_TYPES
    ):
        return {}
    return {
        "fx_booking_context": FxBookingContext(
            initial_publication=(
                idempotency_outcome is TransactionIdempotencyOutcome.CLAIMED
                and command.metadata.processing_intent is TransactionProcessingIntent.STANDARD
                and transaction.epoch is None
                and not correction_claimed
                and not repair_delivery_claimed
            ),
            admitted_epoch=transaction.epoch,
            retention_witness=retention_witness,
        )
    }


def _admitted_position_group(
    command: ProcessTransactionCommand,
    identity: TransactionSemanticIdentity,
    members: tuple[BookedTransaction, ...],
    *,
    correction_claimed: bool,
    repair_claimed: bool,
) -> AdmittedPositionCorrectionGroup | None:
    """Carry successful cost outputs only for the admitted correction or repair route."""
    if not (correction_claimed or repair_claimed):
        return None
    return AdmittedPositionCorrectionGroup(
        root_transaction=command.transaction,
        admission_identity=identity,
        event_id=command.metadata.event_id,
        repair_delivery_id=command.metadata.repair_delivery_id,
        correction_claimed=correction_claimed,
        repair_claimed=repair_claimed,
        members=members,
    )


async def _qualify_first_publication_source(
    command: ProcessTransactionCommand,
    unit_of_work: TransactionProcessingUnitOfWork,
    *,
    idempotency_outcome: TransactionIdempotencyOutcome,
    correction_claimed: bool,
    repair_delivery_claimed: bool,
) -> FirstPublicationSourceAuthority | FxSourceAdmission | None:
    """Retain optional canonical authority only for ordinary first publication."""
    transaction = command.transaction
    if (
        idempotency_outcome is TransactionIdempotencyOutcome.CLAIMED
        and command.metadata.processing_intent is TransactionProcessingIntent.STANDARD
        and transaction.epoch is None
        and not correction_claimed
        and not repair_delivery_claimed
    ):
        source = await unit_of_work.cost.load_first_publication_source(transaction)
        if isinstance(source, FxSourceAdmission):
            authority = source.authority
            return FxSourceAdmission(
                authority if authority is not None and authority.matches(transaction) else None,
                source.retention_witness,
            )
        if isinstance(source, FirstPublicationSourceAuthority) and source.matches(transaction):
            return source
    return None


async def _require_coalesced_financial_authority(
    transaction: BookedTransaction,
    result: PositionProcessingResult,
    unit_of_work: TransactionProcessingUnitOfWork,
    first_publication_source: FirstPublicationSourceAuthority | None = None,
) -> None:
    """Require persisted effects or exact first-publication authority in this UOW."""
    receipt = result.materialized_receipt
    if (
        receipt is not None
        and receipt.tenant_id == transaction.tenant_id
        and receipt.portfolio_id == transaction.portfolio_id
        and receipt.security_id == transaction.security_id
        and receipt.transaction_id == transaction.transaction_id
        and receipt.epoch == result.locked_state_epoch
        and receipt.quantity == result.processed_transaction_quantity
    ):
        if (
            isinstance(first_publication_source, FirstPublicationSourceAuthority)
            and receipt.quantity is not None
            and receipt.quantity.is_finite()
            and receipt.epoch == 0
            and first_publication_source.matches(transaction)
        ):
            return
        financial = await unit_of_work.cost.load_derived_financial_transaction(transaction)
        if (
            financial is not None
            and (
                financial.tenant_id,
                financial.portfolio_id,
                financial.security_id,
                financial.transaction_id,
            )
            == (
                transaction.tenant_id,
                transaction.portfolio_id,
                transaction.security_id,
                transaction.transaction_id,
            )
            and await unit_of_work.cashflow.has_materialized_effect(
                replace(financial, epoch=receipt.epoch), locked_position_epoch=receipt.epoch
            )
        ):
            return
    raise TransactionProcessingRejected(
        reason_code="position_materialization_unavailable",
        detail={
            "portfolio_id": transaction.portfolio_id,
            "security_id": transaction.security_id,
            "transaction_id": transaction.transaction_id,
            "epoch": transaction.epoch,
        },
        retryable=True,
    )


async def _claim_with_legacy_compatibility(
    *,
    idempotency: TransactionIdempotencyPort,
    transaction: BookedTransaction,
    event_id: str,
    correlation_id: str | None,
    identity: TransactionSemanticIdentity,
) -> TransactionIdempotencyOutcome:
    """Claim the current identity while honoring an exact durable v1 claim."""

    outcome = await idempotency.claim(
        tenant_id=transaction.tenant_id or "",
        event_id=event_id,
        portfolio_id=transaction.portfolio_id,
        semantic_key=identity.semantic_key,
        payload_fingerprint=identity.payload_fingerprint,
        correlation_id=correlation_id,
    )
    if outcome is not TransactionIdempotencyOutcome.SEMANTIC_CONFLICT:
        return outcome
    legacy_match = await idempotency.matches_existing_claim(
        tenant_id=transaction.tenant_id or "",
        event_id=event_id,
        portfolio_id=transaction.portfolio_id,
        semantic_key=identity.legacy_semantic_key,
        payload_fingerprint=identity.legacy_payload_fingerprint,
    )
    return TransactionIdempotencyOutcome.PHYSICAL_DUPLICATE if legacy_match else outcome


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


def _bind_materialized_financial_epoch(
    transaction: BookedTransaction,
    locked_position_epochs: dict[tuple[str, str], int],
) -> BookedTransaction:
    if transaction.epoch is not None:
        return transaction
    epoch = locked_position_epochs.get((transaction.portfolio_id, transaction.security_id))
    if epoch is None:
        raise TransactionProcessingRejected(
            reason_code="financial_effect_epoch_unavailable",
            detail={
                "portfolio_id": transaction.portfolio_id,
                "security_id": transaction.security_id,
                "transaction_id": transaction.transaction_id,
            },
            retryable=True,
        )
    return replace(transaction, epoch=epoch)


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


def _requires_canonical_unversioned_repair_source(
    command: ProcessTransactionCommand,
    *,
    idempotency_outcome: TransactionIdempotencyOutcome,
    correction_claimed: bool,
    repair_delivery_claimed: bool,
) -> bool:
    """Distinguish first canonical repair admission from already-owned replay routes."""
    return (
        command.metadata.processing_intent is TransactionProcessingIntent.REPAIR
        and command.transaction.epoch is None
        and idempotency_outcome is TransactionIdempotencyOutcome.CLAIMED
        and not correction_claimed
        and not repair_delivery_claimed
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
        with diagnostic_delivery(
            command.transaction.tenant_id or "",
            command.transaction.portfolio_id,
            command.transaction.transaction_id,
            command.metadata.repair_delivery_id,
        ):
            return await self._execute_observed(command)

    async def _execute_observed(
        self, command: ProcessTransactionCommand
    ) -> ProcessTransactionResult:
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
                idempotency_outcome = await _claim_with_legacy_compatibility(
                    idempotency=unit_of_work.idempotency,
                    transaction=transaction,
                    event_id=metadata.event_id,
                    correlation_id=metadata.correlation_id,
                    identity=identity,
                )
                correction_claimed = False
                if (
                    idempotency_outcome is TransactionIdempotencyOutcome.SEMANTIC_CONFLICT
                    and metadata.processing_intent is TransactionProcessingIntent.REPAIR
                ):
                    identity = build_transaction_correction_identity(transaction)
                    idempotency_outcome = await _claim_with_legacy_compatibility(
                        idempotency=unit_of_work.idempotency,
                        transaction=transaction,
                        event_id=metadata.event_id,
                        correlation_id=metadata.correlation_id,
                        identity=identity,
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
            canonical_unversioned_repair = _requires_canonical_unversioned_repair_source(
                command,
                idempotency_outcome=idempotency_outcome,
                correction_claimed=correction_claimed,
                repair_delivery_claimed=repair_delivery_claimed,
            )
            fx_witness = None
            if canonical_unversioned_repair:
                diagnostic_phase("repair_qualification")
                fx_witness = await unit_of_work.cost.validate_unversioned_repair_source(transaction)
            diagnostic_phase("first_publication_qualification")
            first_publication_source = await _qualify_first_publication_source(
                command,
                unit_of_work,
                idempotency_outcome=idempotency_outcome,
                correction_claimed=correction_claimed,
                repair_delivery_claimed=repair_delivery_claimed,
            )
            if isinstance(first_publication_source, FxSourceAdmission):
                fx_witness = first_publication_source.retention_witness
                first_publication_source = first_publication_source.authority
            with self._observer.observe(TransactionProcessingOperation.COST):
                cost_result = await unit_of_work.cost.process(
                    transaction,
                    correlation_id=metadata.correlation_id,
                    traceparent=metadata.traceparent,
                    reconcile_superseded_derived=correction_claimed,
                    **_fx_booking_arguments(
                        command,
                        idempotency_outcome=idempotency_outcome,
                        correction_claimed=correction_claimed,
                        repair_delivery_claimed=repair_delivery_claimed,
                        retention_witness=fx_witness,
                    ),
                )
            admitted_correction = _admitted_position_group(
                command,
                identity,
                cost_result.processed_transactions,
                correction_claimed=correction_claimed,
                repair_claimed=repair_delivery_claimed or canonical_unversioned_repair,
            )
            position_results = []
            locked_position_epochs: dict[tuple[str, str], int] = {}
            for processed_transaction in cost_result.processed_transactions:
                with self._observer.observe(TransactionProcessingOperation.POSITION):
                    position_result = await unit_of_work.position.process(
                        processed_transaction,
                        correlation_id=metadata.correlation_id,
                        traceparent=metadata.traceparent,
                        rebuild_existing=admitted_correction is not None,
                        admitted_correction=admitted_correction,
                    )
                    position_results.append(position_result)
                    if (
                        processed_transaction.epoch is None
                        and position_result.position_record_count == 0
                        and not position_result.cashflow_rebuild_transactions
                    ):
                        await _require_coalesced_financial_authority(
                            processed_transaction,
                            position_result,
                            unit_of_work,
                            first_publication_source,
                        )
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
            financial_effect_transactions = tuple(
                replace(
                    _bind_materialized_financial_epoch(rebuilt, locked_position_epochs),
                    tenant_id=transaction.tenant_id,
                )
                for rebuilt in financial_effect_transactions
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
                    diagnostic_phase("readiness")
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
