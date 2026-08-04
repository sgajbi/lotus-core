"""Canonical integrity primitives shared by cost-basis receipt writers and readers."""

from collections.abc import Mapping, Sequence, Set
from datetime import date
from decimal import Decimal
from typing import Protocol, cast

from .calculation_lineage import canonical_content_hash
from .transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1

BASIS_TRANSFER_LINEAGE_ALGORITHM_ID = "cost-basis-lot-basis-transfer-allocation"
BASIS_TRANSFER_LINEAGE_ALGORITHM_VERSION = 1


class BasisTransferLineageAllocation(Protocol):
    """Structural allocation facts shared by receipt writers and readers."""

    allocation_ordinal: int
    retained_quantity: Decimal
    source_cost_base_before: Decimal
    source_cost_local_before: Decimal
    source_acquisition_date: date
    source_lot_id: str
    source_transaction_id: str
    transferred_cost_base: Decimal
    transferred_cost_local: Decimal
    retained_cost_base: Decimal
    retained_cost_local: Decimal


def basis_transfer_lineage_input_payload(
    allocations: Sequence[BasisTransferLineageAllocation],
) -> dict[str, object]:
    """Return the closed source-allocation input contract for basis-transfer lineage."""

    return {
        "allocations": [
            {
                "allocation_ordinal": allocation.allocation_ordinal,
                "retained_quantity": allocation.retained_quantity,
                "source_cost_base_before": allocation.source_cost_base_before,
                "source_cost_local_before": allocation.source_cost_local_before,
                "source_acquisition_date": allocation.source_acquisition_date,
                "source_lot_id": allocation.source_lot_id,
                "source_transaction_id": allocation.source_transaction_id,
                "transferred_cost_base": allocation.transferred_cost_base,
                "transferred_cost_local": allocation.transferred_cost_local,
            }
            for allocation in allocations
        ]
    }


def basis_transfer_lineage_output_payload(
    allocations: Sequence[BasisTransferLineageAllocation],
    *,
    transferred_cost_base: Decimal,
    transferred_cost_local: Decimal,
) -> dict[str, object]:
    """Return the closed allocation/aggregate output contract for basis-transfer lineage."""

    return {
        "allocations": [
            {
                "allocation_ordinal": allocation.allocation_ordinal,
                "retained_cost_base": allocation.retained_cost_base,
                "retained_cost_local": allocation.retained_cost_local,
                "source_lot_id": allocation.source_lot_id,
                "transferred_cost_base": allocation.transferred_cost_base,
                "transferred_cost_local": allocation.transferred_cost_local,
            }
            for allocation in allocations
        ],
        "transferred_cost_base": transferred_cost_base,
        "transferred_cost_local": transferred_cost_local,
    }


def canonical_cost_basis_output_payload(
    output_payload: Mapping[str, object],
) -> dict[str, object]:
    """Return the exact policy-scale representation used by persisted receipts."""

    return {
        key: _canonical_cost_basis_output(value, field_path=key)
        for key, value in output_payload.items()
    }


def cost_basis_receipt_semantic_hash(payload: Mapping[str, object]) -> str:
    """Hash one receipt's closed semantic payload at the ledger persistence scale."""

    return cast(str, canonical_content_hash(canonical_cost_basis_output_payload(payload)))


def cost_basis_allocation_content_hash(
    *,
    receipt_id: str,
    payload: Mapping[str, object],
) -> str:
    """Hash one ordered source-lot allocation within a receipt identity."""

    return cost_basis_receipt_semantic_hash({"receipt_id": receipt_id, **payload})


def receipt_version_content_hash(
    *,
    receipt_id: str,
    semantic_content_hash: str,
    receipt_version: int,
    previous_receipt_content_hash: str | None,
) -> str:
    """Hash one immutable receipt version and its predecessor pointer."""

    return cast(
        str,
        canonical_content_hash(
            {
                "previous_receipt_content_hash": previous_receipt_content_hash,
                "receipt_id": receipt_id,
                "receipt_version": receipt_version,
                "semantic_content_hash": semantic_content_hash,
            }
        ),
    )


def _canonical_cost_basis_output(value: object, *, field_path: str) -> object:
    if isinstance(value, Decimal):
        normalized = COST_BASIS_STATE_LEDGER_OUTPUT_V1.normalize(
            value,
            field_name=field_path,
        )
        quantum = Decimal(1).scaleb(-COST_BASIS_STATE_LEDGER_OUTPUT_V1.scale)
        with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
            return normalized.quantize(
                quantum,
                rounding=COST_BASIS_STATE_LEDGER_OUTPUT_V1.rounding,
            )
    if isinstance(value, Mapping):
        return {
            key: _canonical_cost_basis_output(item, field_path=f"{field_path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, Set):
        return {_canonical_cost_basis_output(item, field_path=f"{field_path}[]") for item in value}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _canonical_cost_basis_output(item, field_path=f"{field_path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value
