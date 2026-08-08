"""Prove the shared immutable cost-basis receipt-chain contract."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.domain.cost_basis_receipt_integrity import (
    basis_transfer_lineage_input_payload,
    basis_transfer_lineage_output_payload,
    receipt_version_content_hash,
    verify_cost_basis_receipt_version_chain,
)


@dataclass(frozen=True)
class _ReceiptHeader:
    receipt_id: str
    receipt_version: int
    previous_receipt_content_hash: str | None
    receipt_content_hash: str


@dataclass(frozen=True)
class _BasisTransferAllocation:
    allocation_ordinal: int = 1
    retained_quantity: Decimal = Decimal("7.50")
    source_cost_base_before: Decimal = Decimal("120")
    source_cost_local_before: Decimal = Decimal("100")
    source_acquisition_date: date = date(2026, 1, 1)
    source_lot_id: str = "LOT-1"
    source_transaction_id: str = "BUY-1"
    transferred_cost_base: Decimal = Decimal("30")
    transferred_cost_local: Decimal = Decimal("25.01")
    retained_cost_base: Decimal = Decimal("90")
    retained_cost_local: Decimal = Decimal("74.99")


def _chain(depth: int = 64) -> tuple[_ReceiptHeader, ...]:
    headers: list[_ReceiptHeader] = []
    previous_hash: str | None = None
    for version in range(1, depth + 1):
        content_hash = receipt_version_content_hash(
            receipt_id="receipt:1",
            semantic_content_hash=f"{version:064x}",
            receipt_version=version,
            previous_receipt_content_hash=previous_hash,
        )
        headers.append(
            _ReceiptHeader(
                receipt_id="receipt:1",
                receipt_version=version,
                previous_receipt_content_hash=previous_hash,
                receipt_content_hash=content_hash,
            )
        )
        previous_hash = content_hash
    return tuple(headers)


def test_receipt_version_chain_accepts_complete_depth_sixty_four_history() -> None:
    verify_cost_basis_receipt_version_chain(_chain())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda chain: chain[1:],
            "contiguous and ordered from one",
        ),
        (
            lambda chain: chain[:31] + chain[32:],
            "contiguous and ordered from one",
        ),
        (
            lambda chain: chain[:31] + (chain[30],) + chain[31:],
            "contiguous and ordered from one",
        ),
        (
            lambda chain: (
                chain[:31]
                + (replace(chain[31], previous_receipt_content_hash="f" * 64),)
                + chain[32:]
            ),
            "does not match predecessor",
        ),
        (
            lambda chain: (
                chain[:31] + (replace(chain[31], receipt_id="receipt:other"),) + chain[32:]
            ),
            "multiple receipt identities",
        ),
    ],
)
def test_receipt_version_chain_rejects_noncanonical_middle_history(
    mutation,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        verify_cost_basis_receipt_version_chain(mutation(_chain()))


def test_receipt_version_chain_rejects_empty_or_invalid_hashes() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        verify_cost_basis_receipt_version_chain(())

    chain = _chain()
    with pytest.raises(ValueError, match="receipt_content_hash"):
        verify_cost_basis_receipt_version_chain(
            chain[:31] + (replace(chain[31], receipt_content_hash="invalid"),) + chain[32:]
        )


def test_basis_transfer_lineage_payload_is_invariant_to_database_decimal_scale() -> None:
    allocation = _BasisTransferAllocation()
    persisted = replace(
        allocation,
        retained_quantity=Decimal("7.5000000000"),
        source_cost_base_before=Decimal("120.0000000000"),
        source_cost_local_before=Decimal("100.0000000000"),
        transferred_cost_base=Decimal("30.0000000000"),
        transferred_cost_local=Decimal("25.0100000000"),
        retained_cost_base=Decimal("90.0000000000"),
        retained_cost_local=Decimal("74.9900000000"),
    )

    assert basis_transfer_lineage_input_payload((allocation,)) == (
        basis_transfer_lineage_input_payload((persisted,))
    )
    assert basis_transfer_lineage_output_payload(
        (allocation,),
        transferred_cost_base=allocation.transferred_cost_base,
        transferred_cost_local=allocation.transferred_cost_local,
    ) == basis_transfer_lineage_output_payload(
        (persisted,),
        transferred_cost_base=persisted.transferred_cost_base,
        transferred_cost_local=persisted.transferred_cost_local,
    )
