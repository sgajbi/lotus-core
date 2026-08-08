"""Prove the shared immutable cost-basis receipt-chain contract."""

from dataclasses import dataclass, replace

import pytest
from portfolio_common.domain.cost_basis_receipt_integrity import (
    receipt_version_content_hash,
    verify_cost_basis_receipt_version_chain,
)


@dataclass(frozen=True)
class _ReceiptHeader:
    receipt_id: str
    receipt_version: int
    previous_receipt_content_hash: str | None
    receipt_content_hash: str


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
