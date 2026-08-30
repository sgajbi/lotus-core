"""Read and verify immutable lot-disposal receipts without family assumptions."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    Portfolio,
)
from portfolio_common.domain.calculation_lineage import (
    calculation_lineage_binds_output,
    calculation_lineage_from_payload,
    canonical_content_hash,
    require_sha256_digest,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
    LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
    cost_basis_allocation_content_hash,
    cost_basis_receipt_semantic_hash,
    lot_disposal_allocation_payload,
    lot_disposal_lineage_input_payload,
    lot_disposal_lineage_output_payload,
    receipt_version_content_hash,
    verify_cost_basis_receipt_version_chain,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .lot_disposal_records import (
    LotDisposalAllocationReadRecord,
    LotDisposalReceiptReadRecord,
)


class LotDisposalRepository:
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
        transaction_id: str,
    ) -> tuple[LotDisposalReceiptReadRecord, list[LotDisposalAllocationReadRecord]] | None:
        receipt_statement = (
            select(LotDisposalReceiptRecord)
            .where(
                LotDisposalReceiptRecord.portfolio_id == portfolio_id,
                LotDisposalReceiptRecord.disposal_transaction_id == transaction_id,
            )
            .order_by(LotDisposalReceiptRecord.receipt_version)
        )
        receipts = tuple((await self.db.scalars(receipt_statement)).all())
        if not receipts:
            return None
        receipt_id = str(receipts[0].receipt_id)
        head_version = int(receipts[-1].receipt_version)
        allocation_statement = (
            select(LotDisposalAllocationRecord)
            .where(
                LotDisposalAllocationRecord.receipt_id == receipt_id,
                LotDisposalAllocationRecord.receipt_version <= head_version,
            )
            .order_by(
                LotDisposalAllocationRecord.receipt_version,
                LotDisposalAllocationRecord.allocation_ordinal,
            )
        )
        allocation_rows = tuple((await self.db.scalars(allocation_statement)).all())
        allocations_by_version: defaultdict[int, list[LotDisposalAllocationRecord]] = defaultdict(
            list
        )
        for allocation in allocation_rows:
            allocations_by_version[int(allocation.receipt_version)].append(allocation)
        try:
            verify_cost_basis_receipt_version_chain(receipts)
            for index, receipt in enumerate(receipts):
                _verify_receipt_integrity(
                    receipt,
                    allocations_by_version[int(receipt.receipt_version)],
                    predecessor_hash=(
                        str(receipts[index - 1].receipt_content_hash) if index else None
                    ),
                )
        except ValueError as exc:
            raise CorruptLotDisposalReadModelError(
                f"Persisted lot-disposal receipt chain is corrupt: {receipt_id}"
            ) from exc
        head = receipts[-1]
        head_allocations = allocations_by_version[head_version]
        return _receipt_record(head), [
            _allocation_record(allocation) for allocation in head_allocations
        ]


def _receipt_record(record: LotDisposalReceiptRecord) -> LotDisposalReceiptReadRecord:
    return LotDisposalReceiptReadRecord(
        receipt_id=record.receipt_id,
        receipt_version=record.receipt_version,
        disposal_transaction_id=record.disposal_transaction_id,
        portfolio_id=record.portfolio_id,
        instrument_id=record.instrument_id,
        security_id=record.security_id,
        disposal_timestamp=record.disposal_timestamp,
        transaction_type=record.transaction_type,
        destination_type=record.destination_type,
        target_transaction_id=record.target_transaction_id,
        target_lot_id=record.target_lot_id,
        target_instrument_id=record.target_instrument_id,
        external_destination_reference=record.external_destination_reference,
        cost_basis_method=record.cost_basis_method,
        calculation_policy_id=record.calculation_policy_id,
        calculation_policy_version=record.calculation_policy_version,
        status=record.status,
        void_reason=record.void_reason,
        consumed_quantity=record.consumed_quantity,
        consumed_cost_local=record.consumed_cost_local,
        consumed_cost_base=record.consumed_cost_base,
        allocation_count=record.allocation_count,
        semantic_content_hash=record.semantic_content_hash,
        previous_receipt_content_hash=record.previous_receipt_content_hash,
        receipt_content_hash=record.receipt_content_hash,
        transaction_calculation_lineage=record.transaction_calculation_lineage,
        disposal_calculation_lineage=record.disposal_calculation_lineage,
    )


def _allocation_record(
    record: LotDisposalAllocationRecord,
) -> LotDisposalAllocationReadRecord:
    return LotDisposalAllocationReadRecord(
        allocation_ordinal=record.allocation_ordinal,
        source_lot_id=record.source_lot_id,
        source_transaction_id=record.source_transaction_id,
        source_acquisition_date=record.source_acquisition_date,
        consumed_quantity=record.consumed_quantity,
        consumed_cost_local=record.consumed_cost_local,
        consumed_cost_base=record.consumed_cost_base,
        allocation_content_hash=record.allocation_content_hash,
        amortized_cost_profile_id=record.amortized_cost_profile_id,
        amortized_cost_profile_version=record.amortized_cost_profile_version,
        amortized_cost_profile_content_hash=record.amortized_cost_profile_content_hash,
        amortized_cost_currency=record.amortized_cost_currency,
        amortized_cost_recognized_through=record.amortized_cost_recognized_through,
        amortized_cost_original_quantity=record.amortized_cost_original_quantity,
        amortized_cost_open_quantity_before=record.amortized_cost_open_quantity_before,
        amortized_cost_residual_quantity=record.amortized_cost_residual_quantity,
        amortized_cost_scheduled_local=record.amortized_cost_scheduled_local,
        amortized_cost_current_local=record.amortized_cost_current_local,
        amortized_cost_current_base=record.amortized_cost_current_base,
        amortized_cost_residual_local=record.amortized_cost_residual_local,
        amortized_cost_book_fx_rate_to_base=(record.amortized_cost_book_fx_rate_to_base),
        amortized_cost_residual_base=record.amortized_cost_residual_base,
        amortized_cost_retained_rounding_local=(record.amortized_cost_retained_rounding_local),
        amortized_cost_retained_rounding_base=(record.amortized_cost_retained_rounding_base),
        amortized_cost_calculation_lineage=record.amortized_cost_calculation_lineage,
    )


class CorruptLotDisposalReadModelError(ValueError):
    """Raised when supportability evidence differs from its durable contract."""


def _verify_receipt_integrity(
    receipt: LotDisposalReceiptRecord,
    allocations: list[LotDisposalAllocationRecord],
    *,
    predecessor_hash: str | None,
) -> None:
    """Reconstruct the closed receipt payload and fail closed on any drift."""

    try:
        _verify_header_shape(receipt)
        identity_hash = canonical_content_hash(
            {
                "disposal_transaction_id": receipt.disposal_transaction_id,
                "portfolio_id": receipt.portfolio_id,
                "security_id": receipt.security_id,
            }
        )
        if receipt.receipt_id != f"lot-disposal:{identity_hash}":
            raise ValueError("receipt identity mismatch")
        if receipt.allocation_count != len(allocations):
            raise ValueError("allocation count mismatch")
        ordinals = [allocation.allocation_ordinal for allocation in allocations]
        if ordinals != list(range(1, len(allocations) + 1)):
            raise ValueError("allocation ordinals are not contiguous")
        if len({allocation.source_lot_id for allocation in allocations}) != len(allocations):
            raise ValueError("source lot occurs more than once")
        for allocation in allocations:
            _verify_allocation(receipt, allocation)
        if (
            sum((allocation.consumed_quantity for allocation in allocations), Decimal(0))
            != receipt.consumed_quantity
            or sum((allocation.consumed_cost_local for allocation in allocations), Decimal(0))
            != receipt.consumed_cost_local
            or sum((allocation.consumed_cost_base for allocation in allocations), Decimal(0))
            != receipt.consumed_cost_base
        ):
            raise ValueError("receipt economics do not reconcile to allocations")
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
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise CorruptLotDisposalReadModelError(
            f"Persisted lot-disposal receipt is corrupt: {receipt.receipt_id}"
        ) from exc


def _verify_header_shape(receipt: LotDisposalReceiptRecord) -> None:
    for field_name in (
        "receipt_id",
        "disposal_transaction_id",
        "portfolio_id",
        "instrument_id",
        "security_id",
        "transaction_type",
    ):
        value = getattr(receipt, field_name)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"{field_name} must be canonical nonblank text")
    if not isinstance(receipt.receipt_version, int) or receipt.receipt_version < 1:
        raise ValueError("receipt version must be positive")
    if receipt.cost_basis_method not in {"FIFO", "AVCO"}:
        raise ValueError("unsupported cost basis method")
    if (receipt.calculation_policy_id is None) != (receipt.calculation_policy_version is None):
        raise ValueError("calculation policy identity is incomplete")
    if receipt.disposal_timestamp.tzinfo is None or receipt.disposal_timestamp.utcoffset() is None:
        raise ValueError("disposal timestamp must be timezone-aware")
    if receipt.transaction_calculation_lineage is None:
        raise ValueError("transaction calculation lineage is required")
    calculation_lineage_from_payload(receipt.transaction_calculation_lineage)
    _verify_destination(receipt)


def _verify_destination(receipt: LotDisposalReceiptRecord) -> None:
    destination_values = (
        receipt.destination_type,
        receipt.target_transaction_id,
        receipt.target_lot_id,
        receipt.target_instrument_id,
        receipt.external_destination_reference,
    )
    if all(value is None for value in destination_values):
        return
    if receipt.destination_type == "INTERNAL_LOT":
        if not all(
            isinstance(value, str) and value.strip() == value and value
            for value in (
                receipt.target_transaction_id,
                receipt.target_lot_id,
                receipt.target_instrument_id,
            )
        ):
            raise ValueError("internal destination identity is incomplete")
        if receipt.target_lot_id != f"LOT-{receipt.target_transaction_id}":
            raise ValueError("internal destination lot identity mismatch")
        if receipt.external_destination_reference is not None:
            raise ValueError("internal destination has an external reference")
        return
    if receipt.destination_type == "EXTERNAL_TRANSFER":
        reference = receipt.external_destination_reference
        if not isinstance(reference, str) or not reference or reference.strip() != reference:
            raise ValueError("external destination reference is missing")
        if any(
            value is not None
            for value in (
                receipt.target_transaction_id,
                receipt.target_lot_id,
                receipt.target_instrument_id,
            )
        ):
            raise ValueError("external destination has internal target identity")
        return
    raise ValueError("unknown disposal destination type")


def _verify_allocation(
    receipt: LotDisposalReceiptRecord,
    allocation: LotDisposalAllocationRecord,
) -> None:
    if (
        allocation.portfolio_id != receipt.portfolio_id
        or allocation.security_id != receipt.security_id
        or allocation.receipt_id != receipt.receipt_id
        or allocation.receipt_version != receipt.receipt_version
    ):
        raise ValueError("allocation scope differs from receipt scope")
    if (
        not isinstance(allocation.consumed_quantity, Decimal)
        or not allocation.consumed_quantity.is_finite()
        or allocation.consumed_quantity <= 0
    ):
        raise ValueError("allocation quantity must be finite and positive")
    for field_name in ("consumed_cost_local", "consumed_cost_base"):
        value = getattr(allocation, field_name)
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError(f"{field_name} must be finite and non-negative")
    payload = _allocation_payload(receipt, allocation)
    if allocation.allocation_content_hash != cost_basis_allocation_content_hash(
        receipt_id=receipt.receipt_id,
        payload=payload,
    ):
        raise ValueError("allocation content hash mismatch")


def _verify_lifecycle(
    receipt: LotDisposalReceiptRecord,
    allocations: list[LotDisposalAllocationRecord],
) -> None:
    if receipt.status == "ACTIVE":
        if receipt.consumed_quantity <= 0 or not allocations:
            raise ValueError("active receipt lacks positive allocations")
        lineage = calculation_lineage_from_payload(receipt.disposal_calculation_lineage)
        if lineage is None:
            raise ValueError("active receipt lacks disposal lineage")
        if (
            lineage.algorithm_id != LOT_DISPOSAL_LINEAGE_ALGORITHM_ID
            or lineage.algorithm_version != LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION
        ):
            raise ValueError("disposal lineage algorithm identity is unsupported")
        numeric_policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity()
        if (
            lineage.intermediate_precision != numeric_policy.working_precision
            or lineage.numeric_output_policy != numeric_policy
        ):
            raise ValueError("disposal lineage numeric policy is unsupported")
        if lineage.input_content_hash != canonical_content_hash(
            lot_disposal_lineage_input_payload(
                [_allocation_payload(receipt, allocation) for allocation in allocations]
            )
        ):
            raise ValueError("disposal lineage does not bind persisted inputs")
        if not calculation_lineage_binds_output(
            lineage,
            output_payload=lot_disposal_lineage_output_payload(
                consumed_cost_base=receipt.consumed_cost_base,
                consumed_cost_local=receipt.consumed_cost_local,
                consumed_quantity=receipt.consumed_quantity,
            ),
        ):
            raise ValueError("disposal lineage does not bind persisted outputs")
        if receipt.void_reason is not None:
            raise ValueError("active receipt has a void reason")
        return
    if receipt.status != "VOIDED":
        raise ValueError("unknown receipt status")
    if (
        receipt.consumed_quantity
        or receipt.consumed_cost_local
        or receipt.consumed_cost_base
        or allocations
        or receipt.disposal_calculation_lineage is not None
        or not isinstance(receipt.void_reason, str)
        or not receipt.void_reason.strip()
    ):
        raise ValueError("voided receipt carries invalid economics or lineage")


def _allocation_payload(
    receipt: LotDisposalReceiptRecord,
    allocation: LotDisposalAllocationRecord,
) -> dict[str, object]:
    amortized_evidence = _amortized_cost_evidence_payload(receipt, allocation)
    return lot_disposal_allocation_payload(
        allocation,
        amortized_cost_evidence=amortized_evidence,
    )


_AMORTIZED_EVIDENCE_FIELDS = (
    "amortized_cost_profile_id",
    "amortized_cost_profile_version",
    "amortized_cost_profile_content_hash",
    "amortized_cost_currency",
    "amortized_cost_recognized_through",
    "amortized_cost_original_quantity",
    "amortized_cost_open_quantity_before",
    "amortized_cost_residual_quantity",
    "amortized_cost_scheduled_local",
    "amortized_cost_current_local",
    "amortized_cost_current_base",
    "amortized_cost_residual_local",
    "amortized_cost_book_fx_rate_to_base",
    "amortized_cost_residual_base",
    "amortized_cost_retained_rounding_local",
    "amortized_cost_retained_rounding_base",
    "amortized_cost_calculation_lineage",
)


def _amortized_cost_evidence_payload(
    receipt: LotDisposalReceiptRecord,
    allocation: LotDisposalAllocationRecord,
) -> dict[str, object] | None:
    values = tuple(getattr(allocation, field_name) for field_name in _AMORTIZED_EVIDENCE_FIELDS)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("amortized-cost allocation evidence is only partially persisted")
    _verify_amortized_cost_evidence(receipt, allocation)
    return {
        "book_cost_fx_rate_to_base": allocation.amortized_cost_book_fx_rate_to_base,
        "calculation_lineage": allocation.amortized_cost_calculation_lineage,
        "consumed_cost_base": allocation.consumed_cost_base,
        "consumed_cost_local": allocation.consumed_cost_local,
        "consumed_quantity": allocation.consumed_quantity,
        "currency": allocation.amortized_cost_currency,
        "current_cost_base": allocation.amortized_cost_current_base,
        "current_cost_local": allocation.amortized_cost_current_local,
        "disposal_date": receipt.disposal_timestamp.date(),
        "open_quantity_before": allocation.amortized_cost_open_quantity_before,
        "original_quantity": allocation.amortized_cost_original_quantity,
        "profile_content_hash": allocation.amortized_cost_profile_content_hash,
        "profile_id": allocation.amortized_cost_profile_id,
        "profile_version": allocation.amortized_cost_profile_version,
        "recognized_through_date": allocation.amortized_cost_recognized_through,
        "residual_cost_base": allocation.amortized_cost_residual_base,
        "residual_cost_local": allocation.amortized_cost_residual_local,
        "residual_quantity": allocation.amortized_cost_residual_quantity,
        "retained_rounding_residual_base": (allocation.amortized_cost_retained_rounding_base),
        "retained_rounding_residual_local": (allocation.amortized_cost_retained_rounding_local),
        "scheduled_cost_local": allocation.amortized_cost_scheduled_local,
    }


def _verify_amortized_cost_evidence(
    receipt: LotDisposalReceiptRecord,
    allocation: LotDisposalAllocationRecord,
) -> None:
    if (
        not isinstance(allocation.amortized_cost_profile_id, str)
        or not allocation.amortized_cost_profile_id.strip()
        or allocation.amortized_cost_profile_id != allocation.amortized_cost_profile_id.strip()
    ):
        raise ValueError("amortized-cost profile id is invalid")
    if (
        not isinstance(allocation.amortized_cost_profile_version, int)
        or allocation.amortized_cost_profile_version < 1
    ):
        raise ValueError("amortized-cost profile version is invalid")
    require_sha256_digest(
        allocation.amortized_cost_profile_content_hash,
        "amortized_cost_profile_content_hash",
    )
    currency = allocation.amortized_cost_currency
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isupper():
        raise ValueError("amortized-cost currency is invalid")
    recognized_through = allocation.amortized_cost_recognized_through
    if (
        type(recognized_through) is not date
        or recognized_through > receipt.disposal_timestamp.date()
    ):
        raise ValueError("amortized-cost recognition date is invalid")
    for field_name in (
        "amortized_cost_original_quantity",
        "amortized_cost_open_quantity_before",
        "amortized_cost_residual_quantity",
        "amortized_cost_scheduled_local",
        "amortized_cost_current_local",
        "amortized_cost_current_base",
        "amortized_cost_residual_local",
        "amortized_cost_book_fx_rate_to_base",
        "amortized_cost_residual_base",
        "amortized_cost_retained_rounding_local",
        "amortized_cost_retained_rounding_base",
    ):
        value = getattr(allocation, field_name)
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{field_name} must be a finite Decimal")
    if (
        allocation.amortized_cost_original_quantity <= 0
        or allocation.amortized_cost_open_quantity_before <= 0
        or allocation.amortized_cost_open_quantity_before
        > allocation.amortized_cost_original_quantity
        or allocation.amortized_cost_residual_quantity < 0
        or allocation.amortized_cost_book_fx_rate_to_base <= 0
    ):
        raise ValueError("amortized-cost quantity or FX evidence is invalid")
    if allocation.consumed_quantity + allocation.amortized_cost_residual_quantity != (
        allocation.amortized_cost_open_quantity_before
    ):
        raise ValueError("amortized-cost quantity does not conserve")
    if allocation.consumed_cost_local + allocation.amortized_cost_residual_local != (
        allocation.amortized_cost_current_local
    ):
        raise ValueError("amortized local cost does not conserve")
    if allocation.consumed_cost_base + allocation.amortized_cost_residual_base != (
        allocation.amortized_cost_current_base
    ):
        raise ValueError("amortized base cost does not conserve")
    lineage = calculation_lineage_from_payload(allocation.amortized_cost_calculation_lineage)
    if not calculation_lineage_binds_output(
        lineage,
        output_payload=_amortized_cost_output_payload(allocation),
    ):
        raise ValueError("amortized-cost lineage does not bind persisted evidence")


def _amortized_cost_output_payload(
    allocation: LotDisposalAllocationRecord,
) -> Mapping[str, object]:
    return {
        "consumed_cost_base": allocation.consumed_cost_base,
        "consumed_cost_local": allocation.consumed_cost_local,
        "consumed_quantity": allocation.consumed_quantity,
        "current_cost_base": allocation.amortized_cost_current_base,
        "current_cost_local": allocation.amortized_cost_current_local,
        "open_quantity_before": allocation.amortized_cost_open_quantity_before,
        "recognized_through_date": allocation.amortized_cost_recognized_through,
        "residual_cost_base": allocation.amortized_cost_residual_base,
        "residual_cost_local": allocation.amortized_cost_residual_local,
        "residual_quantity": allocation.amortized_cost_residual_quantity,
        "retained_rounding_residual_base": allocation.amortized_cost_retained_rounding_base,
        "retained_rounding_residual_local": allocation.amortized_cost_retained_rounding_local,
        "scheduled_cost_local": allocation.amortized_cost_scheduled_local,
    }


def _receipt_semantic_payload(
    receipt: LotDisposalReceiptRecord,
    allocations: list[LotDisposalAllocationRecord],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "allocations": [_allocation_payload(receipt, allocation) for allocation in allocations],
        "calculation_policy_id": receipt.calculation_policy_id,
        "calculation_policy_version": receipt.calculation_policy_version,
        "consumed_cost_base": receipt.consumed_cost_base,
        "consumed_cost_local": receipt.consumed_cost_local,
        "consumed_quantity": receipt.consumed_quantity,
        "cost_basis_method": receipt.cost_basis_method,
        "disposal_calculation_lineage": receipt.disposal_calculation_lineage,
        "disposal_timestamp": receipt.disposal_timestamp,
        "disposal_transaction_id": receipt.disposal_transaction_id,
        "instrument_id": receipt.instrument_id,
        "portfolio_id": receipt.portfolio_id,
        "security_id": receipt.security_id,
        "status": receipt.status,
        "transaction_calculation_lineage": receipt.transaction_calculation_lineage,
        "transaction_type": receipt.transaction_type,
        "void_reason": receipt.void_reason,
    }
    if receipt.destination_type is not None:
        payload["destination"] = {
            "destination_type": receipt.destination_type,
            "external_destination_reference": receipt.external_destination_reference,
            "target_instrument_id": receipt.target_instrument_id,
            "target_lot_id": receipt.target_lot_id,
            "target_transaction_id": receipt.target_transaction_id,
        }
    return payload
