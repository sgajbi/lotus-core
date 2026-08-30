"""Read the latest immutable basis-transfer receipt after full-chain verification."""

from collections import defaultdict

from portfolio_common.database_models import (
    LotBasisTransferAllocationRecord,
    LotBasisTransferReceiptRecord,
    Portfolio,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    calculation_lineage_binds_output,
    calculation_lineage_from_payload,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    BASIS_TRANSFER_LINEAGE_ALGORITHM_ID,
    BASIS_TRANSFER_LINEAGE_ALGORITHM_VERSION,
    basis_transfer_lineage_input_payload,
    basis_transfer_lineage_output_payload,
    cost_basis_allocation_content_hash,
    cost_basis_receipt_semantic_hash,
    receipt_version_content_hash,
    verify_cost_basis_receipt_version_chain,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .lot_basis_transfer_records import (
    LotBasisTransferAllocationReadRecord,
    LotBasisTransferReceiptReadRecord,
)


class LotBasisTransferRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def portfolio_exists(self, *, tenant_id: str, portfolio_id: str) -> bool:
        statement = (
            select(Portfolio.portfolio_id)
            .where(
                Portfolio.tenant_id == tenant_id,
                Portfolio.portfolio_id == portfolio_id,
            )
            .limit(1)
        )
        return (await self.db.execute(statement)).scalar_one_or_none() is not None

    async def get_latest_receipt(
        self,
        *,
        portfolio_id: str,
        source_transaction_id: str,
    ) -> (
        tuple[
            LotBasisTransferReceiptReadRecord,
            list[LotBasisTransferAllocationReadRecord],
        ]
        | None
    ):
        receipt_statement = (
            select(LotBasisTransferReceiptRecord)
            .where(
                LotBasisTransferReceiptRecord.portfolio_id == portfolio_id,
                LotBasisTransferReceiptRecord.source_transaction_id == source_transaction_id,
            )
            .order_by(LotBasisTransferReceiptRecord.receipt_version)
        )
        receipt_rows = tuple((await self.db.scalars(receipt_statement)).all())
        if not receipt_rows:
            return None
        receipt_id = str(receipt_rows[0].receipt_id)
        head_version = int(receipt_rows[-1].receipt_version)
        allocation_statement = (
            select(LotBasisTransferAllocationRecord)
            .where(
                LotBasisTransferAllocationRecord.receipt_id == receipt_id,
                LotBasisTransferAllocationRecord.receipt_version <= head_version,
            )
            .order_by(
                LotBasisTransferAllocationRecord.receipt_version,
                LotBasisTransferAllocationRecord.allocation_ordinal,
            )
        )
        allocation_rows = tuple((await self.db.scalars(allocation_statement)).all())
        allocations_by_version: defaultdict[int, list[LotBasisTransferAllocationRecord]] = (
            defaultdict(list)
        )
        for allocation in allocation_rows:
            allocations_by_version[int(allocation.receipt_version)].append(allocation)
        try:
            verify_cost_basis_receipt_version_chain(receipt_rows)
            verified: list[
                tuple[
                    LotBasisTransferReceiptReadRecord,
                    list[LotBasisTransferAllocationReadRecord],
                ]
            ] = []
            for index, receipt_row in enumerate(receipt_rows):
                receipt = _receipt_record(receipt_row)
                allocations = [
                    _allocation_record(allocation)
                    for allocation in allocations_by_version[int(receipt_row.receipt_version)]
                ]
                _verify_receipt_integrity(
                    receipt,
                    allocations,
                    predecessor_hash=(
                        str(receipt_rows[index - 1].receipt_content_hash) if index else None
                    ),
                )
                verified.append((receipt, allocations))
        except ValueError as exc:
            raise CorruptLotBasisTransferReadModelError(
                f"Persisted lot basis-transfer receipt chain is corrupt: {receipt_id}"
            ) from exc
        return verified[-1]


def _receipt_record(record: LotBasisTransferReceiptRecord) -> LotBasisTransferReceiptReadRecord:
    return LotBasisTransferReceiptReadRecord(
        receipt_id=record.receipt_id,
        receipt_version=record.receipt_version,
        source_transaction_id=record.source_transaction_id,
        target_transaction_id=record.target_transaction_id,
        target_lot_id=record.target_lot_id,
        portfolio_id=record.portfolio_id,
        source_instrument_id=record.source_instrument_id,
        source_security_id=record.source_security_id,
        target_instrument_id=record.target_instrument_id,
        transfer_timestamp=record.transfer_timestamp,
        transaction_type=record.transaction_type,
        cost_basis_method=record.cost_basis_method,
        calculation_policy_id=record.calculation_policy_id,
        calculation_policy_version=record.calculation_policy_version,
        status=record.status,
        void_reason=record.void_reason,
        transferred_cost_local=record.transferred_cost_local,
        transferred_cost_base=record.transferred_cost_base,
        allocation_count=record.allocation_count,
        semantic_content_hash=record.semantic_content_hash,
        previous_receipt_content_hash=record.previous_receipt_content_hash,
        receipt_content_hash=record.receipt_content_hash,
        transaction_calculation_lineage=record.transaction_calculation_lineage,
        basis_transfer_calculation_lineage=record.basis_transfer_calculation_lineage,
    )


def _allocation_record(
    record: LotBasisTransferAllocationRecord,
) -> LotBasisTransferAllocationReadRecord:
    return LotBasisTransferAllocationReadRecord(
        allocation_ordinal=record.allocation_ordinal,
        source_lot_id=record.source_lot_id,
        source_transaction_id=record.source_transaction_id,
        source_acquisition_date=record.source_acquisition_date,
        retained_quantity=record.retained_quantity,
        source_cost_local_before=record.source_cost_local_before,
        source_cost_base_before=record.source_cost_base_before,
        transferred_cost_local=record.transferred_cost_local,
        transferred_cost_base=record.transferred_cost_base,
        retained_cost_local=record.retained_cost_local,
        retained_cost_base=record.retained_cost_base,
        allocation_content_hash=record.allocation_content_hash,
    )


class CorruptLotBasisTransferReadModelError(ValueError):
    """Raised when supportability evidence differs from its durable hash contract."""


def _verify_receipt_integrity(
    receipt: LotBasisTransferReceiptReadRecord,
    allocations: list[LotBasisTransferAllocationReadRecord],
    *,
    predecessor_hash: str | None,
) -> None:
    try:
        identity_hash = canonical_content_hash(
            {
                "portfolio_id": receipt.portfolio_id,
                "source_security_id": receipt.source_security_id,
                "source_transaction_id": receipt.source_transaction_id,
            }
        )
        if receipt.receipt_id != f"lot-basis-transfer:{identity_hash}":
            raise ValueError("receipt identity mismatch")
        if receipt.allocation_count != len(allocations):
            raise ValueError("allocation count mismatch")
        ordinals = [allocation.allocation_ordinal for allocation in allocations]
        if ordinals != list(range(1, len(allocations) + 1)):
            raise ValueError("allocation ordinals are not contiguous")
        if len({allocation.source_lot_id for allocation in allocations}) != len(allocations):
            raise ValueError("source lot occurs more than once")
        for allocation in allocations:
            if (
                allocation.transferred_cost_local + allocation.retained_cost_local
                != allocation.source_cost_local_before
                or allocation.transferred_cost_base + allocation.retained_cost_base
                != allocation.source_cost_base_before
            ):
                raise ValueError("source lot basis does not reconcile")
            if allocation.allocation_content_hash != cost_basis_allocation_content_hash(
                receipt_id=receipt.receipt_id,
                payload=_allocation_payload(allocation),
            ):
                raise ValueError("allocation content hash mismatch")
        if (
            sum(
                (allocation.transferred_cost_local for allocation in allocations),
                start=receipt.transferred_cost_local * 0,
            )
            != receipt.transferred_cost_local
            or sum(
                (allocation.transferred_cost_base for allocation in allocations),
                start=receipt.transferred_cost_base * 0,
            )
            != receipt.transferred_cost_base
        ):
            raise ValueError("receipt basis does not reconcile to allocations")
        _verify_calculation_lineage(receipt, allocations)
        _verify_lifecycle(receipt, allocations)
        expected_semantic_hash = cost_basis_receipt_semantic_hash(
            _receipt_semantic_payload(receipt, allocations)
        )
        if receipt.semantic_content_hash != expected_semantic_hash:
            raise ValueError("semantic content hash mismatch")
        if receipt.receipt_version == 1:
            if receipt.previous_receipt_content_hash is not None or predecessor_hash is not None:
                raise ValueError("first receipt version has a predecessor")
        elif predecessor_hash is None or receipt.previous_receipt_content_hash != predecessor_hash:
            raise ValueError("receipt predecessor chain mismatch")
        if receipt.receipt_content_hash != receipt_version_content_hash(
            receipt_id=receipt.receipt_id,
            semantic_content_hash=receipt.semantic_content_hash,
            receipt_version=receipt.receipt_version,
            previous_receipt_content_hash=receipt.previous_receipt_content_hash,
        ):
            raise ValueError("receipt content hash mismatch")
    except (TypeError, ValueError) as exc:
        raise CorruptLotBasisTransferReadModelError(
            f"Persisted lot basis-transfer receipt is corrupt: {receipt.receipt_id}"
        ) from exc


def _verify_calculation_lineage(
    receipt: LotBasisTransferReceiptReadRecord,
    allocations: list[LotBasisTransferAllocationReadRecord],
) -> None:
    """Reconstruct strict lineage and bind active transfer evidence to persisted facts."""

    _required_calculation_lineage(
        receipt.transaction_calculation_lineage,
        label="transaction calculation lineage",
    )
    if receipt.status != "ACTIVE":
        return
    lineage = _required_calculation_lineage(
        receipt.basis_transfer_calculation_lineage,
        label="basis-transfer calculation lineage",
    )
    if (
        lineage.algorithm_id != BASIS_TRANSFER_LINEAGE_ALGORITHM_ID
        or lineage.algorithm_version != BASIS_TRANSFER_LINEAGE_ALGORITHM_VERSION
    ):
        raise ValueError("basis-transfer lineage algorithm identity is unsupported")
    expected_numeric_policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity()
    if (
        lineage.intermediate_precision != expected_numeric_policy.working_precision
        or lineage.numeric_output_policy != expected_numeric_policy
    ):
        raise ValueError("basis-transfer lineage numeric policy is unsupported")
    if lineage.input_content_hash != canonical_content_hash(
        basis_transfer_lineage_input_payload(allocations)
    ):
        raise ValueError("basis-transfer lineage does not bind persisted inputs")
    if not calculation_lineage_binds_output(
        lineage,
        output_payload=basis_transfer_lineage_output_payload(
            allocations,
            transferred_cost_base=receipt.transferred_cost_base,
            transferred_cost_local=receipt.transferred_cost_local,
        ),
    ):
        raise ValueError("basis-transfer lineage does not bind persisted outputs")


def _required_calculation_lineage(payload: object, *, label: str) -> CalculationLineage:
    lineage = calculation_lineage_from_payload(payload)
    if lineage is None:
        raise ValueError(f"{label} is required")
    return lineage


def _verify_lifecycle(
    receipt: LotBasisTransferReceiptReadRecord,
    allocations: list[LotBasisTransferAllocationReadRecord],
) -> None:
    if receipt.status == "ACTIVE":
        if not allocations or receipt.basis_transfer_calculation_lineage is None:
            raise ValueError("active receipt lacks allocations or calculation lineage")
        if receipt.void_reason is not None:
            raise ValueError("active receipt has a void reason")
        if not receipt.transferred_cost_local and not receipt.transferred_cost_base:
            raise ValueError("active receipt lacks basis movement")
        return
    if receipt.status != "VOIDED":
        raise ValueError("unknown receipt status")
    if (
        allocations
        or receipt.transferred_cost_local
        or receipt.transferred_cost_base
        or receipt.basis_transfer_calculation_lineage is not None
        or not receipt.void_reason
    ):
        raise ValueError("voided receipt carries invalid economics or lineage")


def _allocation_payload(
    allocation: LotBasisTransferAllocationReadRecord,
) -> dict[str, object]:
    return {
        "allocation_ordinal": allocation.allocation_ordinal,
        "retained_cost_base": allocation.retained_cost_base,
        "retained_cost_local": allocation.retained_cost_local,
        "retained_quantity": allocation.retained_quantity,
        "source_acquisition_date": allocation.source_acquisition_date,
        "source_cost_base_before": allocation.source_cost_base_before,
        "source_cost_local_before": allocation.source_cost_local_before,
        "source_lot_id": allocation.source_lot_id,
        "source_transaction_id": allocation.source_transaction_id,
        "transferred_cost_base": allocation.transferred_cost_base,
        "transferred_cost_local": allocation.transferred_cost_local,
    }


def _receipt_semantic_payload(
    receipt: LotBasisTransferReceiptReadRecord,
    allocations: list[LotBasisTransferAllocationReadRecord],
) -> dict[str, object]:
    return {
        "allocations": [_allocation_payload(allocation) for allocation in allocations],
        "basis_transfer_calculation_lineage": receipt.basis_transfer_calculation_lineage,
        "calculation_policy_id": receipt.calculation_policy_id,
        "calculation_policy_version": receipt.calculation_policy_version,
        "cost_basis_method": receipt.cost_basis_method,
        "portfolio_id": receipt.portfolio_id,
        "source_instrument_id": receipt.source_instrument_id,
        "source_security_id": receipt.source_security_id,
        "source_transaction_id": receipt.source_transaction_id,
        "status": receipt.status,
        "target_lot_id": receipt.target_lot_id,
        "target_instrument_id": receipt.target_instrument_id,
        "target_transaction_id": receipt.target_transaction_id,
        "transaction_calculation_lineage": receipt.transaction_calculation_lineage,
        "transaction_type": receipt.transaction_type,
        "transfer_timestamp": receipt.transfer_timestamp,
        "transferred_cost_base": receipt.transferred_cost_base,
        "transferred_cost_local": receipt.transferred_cost_local,
        "void_reason": receipt.void_reason,
    }
