"""Shared deterministic integrity primitives for append-only cost-basis receipts."""

from typing import cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    calculation_lineage_from_payload,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    receipt_version_content_hash as _receipt_version_content_hash,
)

__all__ = ["receipt_version_content_hash", "required_calculation_lineage"]


def receipt_version_content_hash(
    *,
    receipt_id: str,
    semantic_content_hash: str,
    receipt_version: int,
    previous_receipt_content_hash: str | None,
) -> str:
    """Expose the shared immutable-version hash with a local typed boundary."""

    return cast(
        str,
        _receipt_version_content_hash(
            receipt_id=receipt_id,
            semantic_content_hash=semantic_content_hash,
            receipt_version=receipt_version,
            previous_receipt_content_hash=previous_receipt_content_hash,
        ),
    )


def required_calculation_lineage(payload: object, context: str) -> CalculationLineage:
    """Rehydrate required lineage without coupling receipt adapters to JSON storage."""

    lineage = calculation_lineage_from_payload(payload)
    if lineage is None:
        raise ValueError(f"{context} is required")
    return lineage
