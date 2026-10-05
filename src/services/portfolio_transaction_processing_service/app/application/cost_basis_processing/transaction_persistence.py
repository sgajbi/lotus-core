"""Persist calculated transaction economics through framework-neutral ports."""

from dataclasses import replace
from decimal import Decimal

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    CostBasisProcessingCheckpoint,
    CostBasisTransaction,
    Fees,
    build_cost_basis_engine_input,
    transaction_lot_behavior,
)
from ...domain.transaction import BookedTransaction, build_transaction_semantic_identity
from ...ports import (
    AccruedIncomeOffsetStatePort,
    CostBasisLotStatePort,
    CostBasisPersistenceObservation,
    CostBasisPersistenceObserver,
    CostBasisPersistenceStage,
    CostBasisPersistenceStatus,
    CostBasisTransactionStatePort,
    InitialOpeningCostStatePort,
)
from .persistence_scope import (
    CostBasisTransactionPersistenceScope,
    build_cost_basis_persistence_plan,
)


async def persist_cost_basis_transactions(
    *,
    processed: list[CostBasisTransaction],
    incoming_transaction_ids: set[str],
    incoming_source: BookedTransaction | None = None,
    transactions: CostBasisTransactionStatePort,
    lot_states: CostBasisLotStatePort,
    income_offsets: AccruedIncomeOffsetStatePort,
    initial_opening_state: InitialOpeningCostStatePort | None = None,
    initial_opening_checkpoint: CostBasisProcessingCheckpoint | None = None,
    observer: CostBasisPersistenceObserver | None = None,
    persistence_scope: CostBasisTransactionPersistenceScope = (
        CostBasisTransactionPersistenceScope.AFFECTED_SUFFIX
    ),
    missing_authority_transaction_ids: set[str] | frozenset[str] = frozenset(),
) -> tuple[BookedTransaction, ...]:
    """Persist governed timeline economics and return newly processed transactions."""

    persistence_observer = observer or _NullCostBasisPersistenceObserver()
    if incoming_source is not None:
        _validate_incoming_fee_source(incoming_source, processed, incoming_transaction_ids)
    newly_persisted: list[BookedTransaction] = []
    persistence_plan = build_cost_basis_persistence_plan(
        processed=processed,
        incoming_transaction_ids=incoming_transaction_ids,
        scope=persistence_scope,
        missing_authority_transaction_ids=missing_authority_transaction_ids,
    )
    affected_transaction_ids = {
        transaction.transaction_id for transaction in persistence_plan.child_state_transactions
    }
    acquisition_parent_ids = {
        transaction.transaction_id
        for transaction in persistence_plan.acquisition_parent_transactions
    }
    for transaction in persistence_plan.economics_transactions:
        if transaction.transaction_id in acquisition_parent_ids:
            # Dependency admission is not child-effect replay. The caller's UOW owns
            # this absent-only write and the subsequent disposal reconciliation.
            await lot_states.ensure_acquisition_lot_parent(
                transaction,
                tenant_id=_acquisition_parent_tenant(
                    transaction,
                    processed=processed,
                    incoming_transaction_ids=incoming_transaction_ids,
                ),
            )
        persisted = await _persist_cost_basis_transaction(
            transaction=transaction,
            transactions=transactions,
            lot_states=lot_states,
            income_offsets=income_offsets,
            initial_opening_state=initial_opening_state,
            initial_opening_checkpoint=(
                initial_opening_checkpoint
                if transaction.transaction_id in incoming_transaction_ids
                else None
            ),
            persist_child_state=transaction.transaction_id in affected_transaction_ids,
            observer=persistence_observer,
        )
        if transaction.transaction_id in incoming_transaction_ids:
            if incoming_source is not None:
                persisted = _restore_incoming_fee_presence(persisted, incoming_source)
            newly_persisted.append(persisted)
    return tuple(newly_persisted)


_NAMED_FEE_FIELDS = ("brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees")
_CALCULATED_SOURCE_FIELDS = (
    "tenant_id",
    "portfolio_id",
    "security_id",
    "transaction_id",
    "instrument_id",
    "transaction_date",
    "settlement_date",
    "quantity",
    "gross_transaction_amount",
    "trade_currency",
    "epoch",
)


def _validate_incoming_fee_source(
    source: BookedTransaction,
    processed: list[CostBasisTransaction],
    incoming_ids: set[str],
) -> None:
    roots = [row for row in processed if row.transaction_id == source.transaction_id]
    if incoming_ids != {source.transaction_id} or len(roots) != 1:
        raise ValueError("Incoming fee source requires exactly one calculated root")
    calculated = roots[0]
    if not source.tenant_id or any(
        getattr(calculated, name, None) != getattr(source, name)
        for name in _CALCULATED_SOURCE_FIELDS
    ):
        raise ValueError("Incoming fee source conflicts with calculated root scope or material")
    if normalize_transaction_control_code(calculated.transaction_type) != (
        normalize_transaction_control_code(source.transaction_type)
    ):
        raise ValueError("Incoming fee source conflicts with calculated transaction type")
    expected_input = build_cost_basis_engine_input(source)
    expected_fees = Fees(**expected_input.get("fees", {}))
    calculated_fees = calculated.fees or Fees()
    if any(
        getattr(calculated_fees, name) != getattr(expected_fees, name) for name in _NAMED_FEE_FIELDS
    ) or calculated_fees.total_fees != Decimal(expected_input["trade_fee"]):
        raise ValueError("Incoming fee source conflicts with calculated fees")


def _restore_incoming_fee_presence(
    persisted: BookedTransaction, source: BookedTransaction
) -> BookedTransaction:
    if persisted.tenant_id != source.tenant_id or (
        persisted.epoch is not None and persisted.epoch != source.epoch
    ):
        raise ValueError("Incoming fee source conflicts with returned root scope or epoch")
    if any(
        getattr(persisted, name) is not None and getattr(persisted, name) != getattr(source, name)
        for name in _NAMED_FEE_FIELDS
    ):
        raise ValueError("Incoming fee source conflicts with returned named fees")
    restored = replace(
        persisted,
        brokerage=source.brokerage,
        stamp_duty=source.stamp_duty,
        exchange_fee=source.exchange_fee,
        gst=source.gst,
        other_fees=source.other_fees,
    )
    # The canonical table has no source epoch. Its caller already retains that
    # authority for effect coordination; this comparison does not rewrite it.
    if build_transaction_semantic_identity(replace(restored, epoch=source.epoch)) != (
        build_transaction_semantic_identity(source)
    ):
        raise ValueError("Incoming fee source conflicts with returned root material")
    return restored


def _acquisition_parent_tenant(
    parent: CostBasisTransaction,
    *,
    processed: list[CostBasisTransaction],
    incoming_transaction_ids: set[str],
) -> str:
    # Historical DB transactions carry no tenant column. Borrow only the resolved
    # incoming command authority for the same stream; the adapter verifies it
    # against the source's durable portfolio owner before inserting a parent.
    tenant_ids = {
        getattr(transaction, "tenant_id", None)
        for transaction in processed
        if transaction.transaction_id in incoming_transaction_ids
        and transaction.portfolio_id == parent.portfolio_id
        and transaction.security_id == parent.security_id
    }
    if len(tenant_ids) != 1:
        raise ValueError("Acquisition lot parent requires one incoming stream tenant")
    tenant_id = tenant_ids.pop()
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("Acquisition lot parent requires a resolved incoming stream tenant")
    return tenant_id


async def _persist_cost_basis_transaction(
    *,
    transaction: CostBasisTransaction,
    transactions: CostBasisTransactionStatePort,
    lot_states: CostBasisLotStatePort,
    income_offsets: AccruedIncomeOffsetStatePort,
    initial_opening_state: InitialOpeningCostStatePort | None,
    initial_opening_checkpoint: CostBasisProcessingCheckpoint | None,
    persist_child_state: bool,
    observer: CostBasisPersistenceObserver,
) -> BookedTransaction:
    _observe(
        observer,
        transaction=transaction,
        stage=CostBasisPersistenceStage.TRANSACTION_COSTS,
        status=CostBasisPersistenceStatus.ATTEMPT,
    )
    persisted = await transactions.apply_transaction_costs_and_replace_breakdown(transaction)
    if persisted is None:
        raise ValueError(
            "Canonical transaction row was not found during cost persistence: "
            f"{transaction.transaction_id}"
        )
    _observe(
        observer,
        transaction=transaction,
        stage=CostBasisPersistenceStage.TRANSACTION_COSTS,
        status=CostBasisPersistenceStatus.SUCCESS,
    )

    persisted = replace(persisted, lot_restatement=transaction.lot_restatement)
    if not persist_child_state:
        return persisted

    if initial_opening_checkpoint is not None:
        await _persist_initial_opening_state(
            transaction=transaction,
            checkpoint=initial_opening_checkpoint,
            state=_require_initial_opening_state(initial_opening_state),
            observer=observer,
        )
    elif transaction_lot_behavior(transaction.transaction_type) in LOT_OPENING_BEHAVIORS:
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.OPEN_LOT,
            status=CostBasisPersistenceStatus.ATTEMPT,
        )
        await lot_states.upsert_buy_lot_state(transaction)
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.OPEN_LOT,
            status=CostBasisPersistenceStatus.SUCCESS,
        )

    if (
        normalize_transaction_control_code(transaction.transaction_type) == "BUY"
        and initial_opening_checkpoint is None
    ):
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
            status=CostBasisPersistenceStatus.ATTEMPT,
        )
        await income_offsets.upsert_accrued_income_offset(transaction)
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
            status=CostBasisPersistenceStatus.SUCCESS,
        )

    trade_fee = (
        transaction.fees.total_fees
        if transaction.fees is not None and transaction.fees.total_fees > Decimal(0)
        else Decimal(0)
    )
    return replace(persisted, trade_fee=trade_fee)


async def _persist_initial_opening_state(
    *,
    transaction: CostBasisTransaction,
    checkpoint: CostBasisProcessingCheckpoint,
    state: InitialOpeningCostStatePort,
    observer: CostBasisPersistenceObserver,
) -> None:
    if normalize_transaction_control_code(transaction.transaction_type) != "BUY":
        raise ValueError("Initial opening cost state requires a BUY transaction")
    for stage in (
        CostBasisPersistenceStage.OPEN_LOT,
        CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
    ):
        _observe(
            observer,
            transaction=transaction,
            stage=stage,
            status=CostBasisPersistenceStatus.ATTEMPT,
        )
    await state.persist_initial_opening_cost_state(
        transaction=transaction,
        checkpoint=checkpoint,
    )
    for stage in (
        CostBasisPersistenceStage.OPEN_LOT,
        CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
    ):
        _observe(
            observer,
            transaction=transaction,
            stage=stage,
            status=CostBasisPersistenceStatus.SUCCESS,
        )


def _observe(
    observer: CostBasisPersistenceObserver,
    *,
    transaction: CostBasisTransaction,
    stage: CostBasisPersistenceStage,
    status: CostBasisPersistenceStatus,
) -> None:
    observer.observe(
        CostBasisPersistenceObservation(
            transaction=transaction,
            stage=stage,
            status=status,
        )
    )


class _NullCostBasisPersistenceObserver:
    """Provide no-op observation for isolated application use."""

    def observe(self, observation: CostBasisPersistenceObservation) -> None:
        del observation


def _require_initial_opening_state(
    state: InitialOpeningCostStatePort | None,
) -> InitialOpeningCostStatePort:
    if state is None:
        raise ValueError("Initial opening cost-state persistence port is required")
    return state
