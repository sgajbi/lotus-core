"""Map calculated basis-only movements into immutable receipt state."""

from collections.abc import Sequence, Set

from portfolio_common.domain.calculation_lineage import CalculationLineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from ...domain.cost_basis import (
    CostBasisTransaction,
    LotBasisTransferReceiptState,
    LotBasisTransferReceiptStatus,
    LotBasisTransferReconciliationScope,
    TransactionLotBasisTransfer,
)
from ...ports import CostBasisLotBasisTransferPort
from .persistence_scope import affected_transaction_suffix


async def persist_current_lot_basis_transfers(
    *,
    processed: Sequence[CostBasisTransaction],
    incoming_transaction_ids: Set[str],
    basis_transfers: Sequence[TransactionLotBasisTransfer],
    cost_basis_method: CostBasisMethod,
    repository: CostBasisLotBasisTransferPort,
) -> None:
    """Reconcile basis-transfer evidence for the exact affected timeline suffix."""

    affected = affected_transaction_suffix(
        processed=processed,
        incoming_transaction_ids=incoming_transaction_ids,
    )
    transactions_by_id = {transaction.transaction_id: transaction for transaction in processed}
    affected_ids = tuple(transaction.transaction_id for transaction in affected)
    transfers_by_source: dict[str, TransactionLotBasisTransfer] = {}
    for transfer in basis_transfers:
        source_id = transfer.source_transaction_id
        if source_id not in transactions_by_id:
            raise ValueError(
                "Basis-transfer evidence references a source outside the calculated timeline: "
                f"{source_id}"
            )
        if source_id in transfers_by_source:
            raise ValueError(
                f"Calculated timeline emitted duplicate basis-transfer evidence: {source_id}"
            )
        transfers_by_source[source_id] = transfer

    unexpected = set(transfers_by_source).difference(affected_ids)
    if unexpected:
        raise ValueError(
            "Basis-transfer evidence references a source outside the affected suffix: "
            f"{sorted(unexpected)}"
        )

    await repository.reconcile_basis_transfer_receipts(
        reconciliation_scopes=tuple(
            _reconciliation_scope(
                transaction=transaction,
                cost_basis_method=cost_basis_method,
            )
            for transaction in affected
        ),
        receipt_states=tuple(
            _active_receipt_state(
                source=transactions_by_id[source_id],
                transfer=transfer,
                cost_basis_method=cost_basis_method,
            )
            for source_id, transfer in transfers_by_source.items()
        ),
    )


def _reconciliation_scope(
    *,
    transaction: CostBasisTransaction,
    cost_basis_method: CostBasisMethod,
) -> LotBasisTransferReconciliationScope:
    transaction_lineage = getattr(transaction, "calculation_lineage", None)
    if not isinstance(transaction_lineage, CalculationLineage):
        raise ValueError(
            "Calculated transaction is missing governed calculation lineage for basis-transfer "
            f"reconciliation: {transaction.transaction_id}"
        )
    return LotBasisTransferReconciliationScope(
        source_transaction_id=transaction.transaction_id,
        portfolio_id=transaction.portfolio_id,
        source_instrument_id=transaction.instrument_id,
        source_security_id=transaction.security_id,
        transfer_timestamp=transaction.transaction_date,
        transaction_type=transaction.transaction_type,
        cost_basis_method=cost_basis_method,
        calculation_policy_id=getattr(transaction, "calculation_policy_id", None),
        calculation_policy_version=getattr(transaction, "calculation_policy_version", None),
        transaction_calculation_lineage=transaction_lineage,
    )


def _active_receipt_state(
    *,
    source: CostBasisTransaction,
    transfer: TransactionLotBasisTransfer,
    cost_basis_method: CostBasisMethod,
) -> LotBasisTransferReceiptState:
    transaction_lineage = getattr(source, "calculation_lineage", None)
    if not isinstance(transaction_lineage, CalculationLineage):
        raise ValueError(
            "Calculated transaction is missing governed calculation lineage for basis-transfer "
            f"persistence: {source.transaction_id}"
        )
    transfer_lineage = transfer.result.calculation_lineage
    if not isinstance(transfer_lineage, CalculationLineage):
        raise ValueError(
            "Basis-transfer evidence is missing governed calculation lineage: "
            f"{source.transaction_id}"
        )
    return LotBasisTransferReceiptState(
        source_transaction_id=source.transaction_id,
        target_transaction_id=transfer.target_transaction_id,
        target_lot_id=transfer.target_lot_id,
        portfolio_id=source.portfolio_id,
        source_instrument_id=source.instrument_id,
        source_security_id=source.security_id,
        target_instrument_id=source.target_instrument_id,
        transfer_timestamp=source.transaction_date,
        transaction_type=source.transaction_type,
        cost_basis_method=cost_basis_method,
        calculation_policy_id=getattr(source, "calculation_policy_id", None),
        calculation_policy_version=getattr(source, "calculation_policy_version", None),
        transaction_calculation_lineage=transaction_lineage,
        status=LotBasisTransferReceiptStatus.ACTIVE,
        transferred_cost_local=transfer.result.transferred_cost_local,
        transferred_cost_base=transfer.result.transferred_cost_base,
        allocations=transfer.result.allocations,
        basis_transfer_calculation_lineage=transfer_lineage,
    )
