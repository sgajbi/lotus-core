"""Persist lot-disposal receipts for the exact affected calculation suffix."""

from collections.abc import Sequence, Set
from decimal import Decimal
from typing import cast

from portfolio_common.domain.calculation_lineage import CalculationLineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from ...domain.cost_basis import (
    CostBasisTransaction,
    LotDisposalDestination,
    LotDisposalDestinationType,
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    TransactionLotDisposal,
)
from ...ports import CostBasisLotDisposalPort
from .persistence_scope import affected_transaction_suffix


async def persist_current_lot_disposals(
    *,
    processed: Sequence[CostBasisTransaction],
    incoming_transaction_ids: Set[str],
    disposals: Sequence[TransactionLotDisposal],
    cost_basis_method: CostBasisMethod,
    repository: CostBasisLotDisposalPort,
) -> None:
    """Reconcile immutable disposal evidence with the affected transaction suffix."""

    affected = affected_transaction_suffix(
        processed=processed,
        incoming_transaction_ids=incoming_transaction_ids,
    )
    processed_ids = {transaction.transaction_id for transaction in processed}
    disposals_by_transaction: dict[str, TransactionLotDisposal] = {}
    for disposal in disposals:
        transaction_id = disposal.disposal_transaction_id
        if transaction_id not in processed_ids:
            raise ValueError(
                "Lot-disposal evidence references a transaction outside the calculated timeline: "
                f"{transaction_id}"
            )
        if transaction_id in disposals_by_transaction:
            raise ValueError(
                f"Calculated timeline emitted duplicate lot-disposal evidence: {transaction_id}"
            )
        disposals_by_transaction[transaction_id] = disposal

    await repository.reconcile_disposal_receipts(
        receipt_states=tuple(
            _receipt_state(
                transaction=transaction,
                disposal=disposals_by_transaction.get(transaction.transaction_id),
                cost_basis_method=cost_basis_method,
            )
            for transaction in affected
        ),
    )


def _receipt_state(
    *,
    transaction: CostBasisTransaction,
    disposal: TransactionLotDisposal | None,
    cost_basis_method: CostBasisMethod,
) -> LotDisposalReceiptState:
    transaction_lineage = getattr(transaction, "calculation_lineage", None)
    if not isinstance(transaction_lineage, CalculationLineage):
        raise ValueError(
            "Calculated transaction is missing governed calculation lineage for disposal "
            f"persistence: {transaction.transaction_id}"
        )
    shared = {
        "disposal_transaction_id": transaction.transaction_id,
        "portfolio_id": transaction.portfolio_id,
        "instrument_id": transaction.instrument_id,
        "security_id": transaction.security_id,
        "disposal_timestamp": transaction.transaction_date,
        "transaction_type": transaction.transaction_type,
        "cost_basis_method": cost_basis_method,
        "calculation_policy_id": getattr(transaction, "calculation_policy_id", None),
        "calculation_policy_version": getattr(transaction, "calculation_policy_version", None),
        "transaction_calculation_lineage": transaction_lineage,
    }
    if disposal is None:
        return LotDisposalReceiptState(
            **shared,
            status=LotDisposalReceiptStatus.VOIDED,
            consumed_quantity=Decimal(0),
            consumed_cost_local=Decimal(0),
            consumed_cost_base=Decimal(0),
            allocations=(),
            disposal_calculation_lineage=None,
            void_reason="RECALCULATED_WITHOUT_LOT_DISPOSAL",
        )
    disposal_lineage = disposal.result.calculation_lineage
    if not isinstance(disposal_lineage, CalculationLineage):
        raise ValueError(
            "Lot-disposal evidence is missing governed calculation lineage: "
            f"{transaction.transaction_id}"
        )
    return LotDisposalReceiptState(
        **shared,
        status=LotDisposalReceiptStatus.ACTIVE,
        consumed_quantity=disposal.result.consumed_quantity,
        consumed_cost_local=disposal.result.cost_local,
        consumed_cost_base=disposal.result.cost_base,
        allocations=disposal.result.allocations,
        disposal_calculation_lineage=disposal_lineage,
        destination=_internal_lot_destination(transaction),
    )


_INTERNAL_LOT_DISPOSAL_TYPES = frozenset(
    {
        "EXCHANGE_OUT",
        "MERGER_OUT",
        "REPLACEMENT_OUT",
    }
)


def _internal_lot_destination(
    transaction: CostBasisTransaction,
) -> LotDisposalDestination | None:
    if transaction.transaction_type not in _INTERNAL_LOT_DISPOSAL_TYPES:
        return None
    target_transaction_id = getattr(transaction, "target_transaction_reference", None)
    target_instrument_id = transaction.target_instrument_id
    missing_fields = tuple(
        field_name
        for field_name, value in (
            ("target_transaction_reference", target_transaction_id),
            ("target_instrument_id", target_instrument_id),
        )
        if not isinstance(value, str) or not value.strip()
    )
    if missing_fields:
        raise ValueError(
            f"{transaction.transaction_type} disposal destination requires "
            + " and ".join(missing_fields)
            + f": {transaction.transaction_id}"
        )
    normalized_target_transaction_id = cast(str, target_transaction_id).strip()
    return LotDisposalDestination(
        destination_type=LotDisposalDestinationType.INTERNAL_LOT,
        target_transaction_id=normalized_target_transaction_id,
        target_lot_id=f"LOT-{normalized_target_transaction_id}",
        target_instrument_id=cast(str, target_instrument_id).strip(),
    )
