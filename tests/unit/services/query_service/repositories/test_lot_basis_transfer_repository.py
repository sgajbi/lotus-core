"""Verify bounded latest-version lot basis-transfer receipt queries."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.cost_basis_receipt_integrity import (
    cost_basis_allocation_content_hash,
    cost_basis_receipt_semantic_hash,
    receipt_version_content_hash,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.lot_basis_transfer_records import (
    LotBasisTransferAllocationReadRecord,
    LotBasisTransferReceiptReadRecord,
)
from src.services.query_service.app.repositories.lot_basis_transfer_repository import (
    CorruptLotBasisTransferReadModelError,
    LotBasisTransferRepository,
    _allocation_payload,
    _receipt_semantic_payload,
    _verify_lifecycle,
    _verify_receipt_integrity,
)


@pytest.mark.asyncio
async def test_latest_receipt_uses_one_scoped_latest_version_query() -> None:
    receipt = MagicMock(receipt_id="RECEIPT-1", allocation_count=2)
    first = MagicMock(source_lot_id="LOT-1")
    second = MagicMock(source_lot_id="LOT-2")
    result = MagicMock()
    result.all.return_value = [(receipt, first, None), (receipt, second, None)]
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=result)

    with patch(
        "src.services.query_service.app.repositories.lot_basis_transfer_repository."
        "_verify_receipt_integrity"
    ) as verify:
        resolved = await LotBasisTransferRepository(session).get_latest_receipt(
            portfolio_id="P1",
            source_transaction_id="DEMERGER-OUT-001",
        )

    assert resolved is not None
    mapped_receipt, mapped_allocations = resolved
    assert isinstance(mapped_receipt, LotBasisTransferReceiptReadRecord)
    assert mapped_receipt.receipt_id == "RECEIPT-1"
    assert all(isinstance(row, LotBasisTransferAllocationReadRecord) for row in mapped_allocations)
    assert [row.source_lot_id for row in mapped_allocations] == ["LOT-1", "LOT-2"]
    session.execute.assert_awaited_once()
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "LEFT OUTER JOIN lot_basis_transfer_allocations" in compiled
    assert "max(lot_basis_transfer_receipts.receipt_version)" in compiled
    assert "lot_basis_transfer_receipts.portfolio_id = 'P1'" in compiled
    assert "lot_basis_transfer_receipts.source_transaction_id = 'DEMERGER-OUT-001'" in compiled
    assert "ORDER BY lot_basis_transfer_allocations.allocation_ordinal ASC" in compiled
    verify.assert_called_once()


@pytest.mark.asyncio
async def test_portfolio_existence_and_absent_receipt_are_bounded() -> None:
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.side_effect = ["P1", None]
    empty_result = MagicMock()
    empty_result.all.return_value = []
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=[scalar_result, scalar_result, empty_result])
    repository = LotBasisTransferRepository(session)

    assert await repository.portfolio_exists("P1") is True
    assert await repository.portfolio_exists("MISSING") is False
    assert (
        await repository.get_latest_receipt(
            portfolio_id="P1",
            source_transaction_id="UNKNOWN",
        )
        is None
    )


def test_latest_receipt_fails_closed_on_missing_allocation_rows() -> None:
    receipt, allocation = _valid_evidence()

    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt"):
        _verify_receipt_integrity(receipt, [], predecessor_hash=None)


def test_latest_receipt_fails_closed_on_tampered_allocation_hash() -> None:
    receipt, allocation = _valid_evidence()
    tampered = replace(allocation, allocation_content_hash="0" * 64)

    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt"):
        _verify_receipt_integrity(receipt, [tampered], predecessor_hash=None)


def test_latest_receipt_verifies_immediate_predecessor_hash() -> None:
    receipt, allocation = _valid_evidence()
    predecessor_hash = "e" * 64
    receipt = replace(
        receipt,
        receipt_version=2,
        previous_receipt_content_hash=predecessor_hash,
        receipt_content_hash=receipt_version_content_hash(
            receipt_id=receipt.receipt_id,
            semantic_content_hash=receipt.semantic_content_hash,
            receipt_version=2,
            previous_receipt_content_hash=predecessor_hash,
        ),
    )

    _verify_receipt_integrity(receipt, [allocation], predecessor_hash=predecessor_hash)
    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt"):
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash="f" * 64)


def test_integrity_rejects_identity_order_uniqueness_and_hash_drift() -> None:
    receipt, allocation = _valid_evidence()
    _assert_corrupt(
        replace(receipt, receipt_id="lot-basis-transfer:wrong"), [allocation], "identity"
    )
    _assert_corrupt(replace(receipt, allocation_count=2), [allocation], "allocation count")
    _assert_corrupt(
        receipt,
        [replace(allocation, allocation_ordinal=2)],
        "ordinals are not contiguous",
    )
    _assert_corrupt(
        replace(receipt, allocation_count=2),
        [allocation, replace(allocation, allocation_ordinal=2)],
        "source lot occurs more than once",
    )
    _assert_corrupt(
        replace(receipt, transferred_cost_local=Decimal("24")),
        [allocation],
        "receipt basis does not reconcile",
    )
    _assert_corrupt(
        replace(receipt, semantic_content_hash="0" * 64),
        [allocation],
        "semantic content hash mismatch",
    )
    _assert_corrupt(
        replace(receipt, previous_receipt_content_hash="e" * 64),
        [allocation],
        "first receipt version has a predecessor",
    )
    _assert_corrupt(
        replace(receipt, receipt_content_hash="0" * 64),
        [allocation],
        "receipt content hash mismatch",
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"transferred_cost_local": Decimal("24")}, "source lot basis does not reconcile"),
        ({"transferred_cost_base": Decimal("17")}, "source lot basis does not reconcile"),
    ],
)
def test_integrity_rejects_nonconserving_source_lot_basis(
    changes: dict[str, object],
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    tampered = replace(allocation, **changes)
    _assert_corrupt(receipt, [tampered], reason)


@pytest.mark.parametrize(
    ("receipt_changes", "reason"),
    [
        ({"basis_transfer_calculation_lineage": None}, "lacks allocations"),
        ({"void_reason": "incorrect"}, "active receipt has a void reason"),
        (
            {"transferred_cost_local": Decimal(0), "transferred_cost_base": Decimal(0)},
            "active receipt lacks basis movement",
        ),
        ({"status": "UNKNOWN"}, "unknown receipt status"),
    ],
)
def test_lifecycle_rejects_inconsistent_active_or_unknown_state(
    receipt_changes: dict[str, object],
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    with pytest.raises(ValueError, match=reason):
        _verify_lifecycle(replace(receipt, **receipt_changes), [allocation])


def test_lifecycle_accepts_closed_void_and_rejects_void_with_economics() -> None:
    receipt, allocation = _valid_evidence()
    voided = replace(
        receipt,
        status="VOIDED",
        transferred_cost_local=Decimal(0),
        transferred_cost_base=Decimal(0),
        basis_transfer_calculation_lineage=None,
        void_reason="SUPERSEDED",
    )

    _verify_lifecycle(voided, [])
    with pytest.raises(ValueError, match="voided receipt carries invalid economics"):
        _verify_lifecycle(voided, [allocation])


def _valid_evidence() -> tuple[
    LotBasisTransferReceiptReadRecord,
    LotBasisTransferAllocationReadRecord,
]:
    allocation = LotBasisTransferAllocationReadRecord(
        allocation_ordinal=1,
        source_lot_id="LOT-BUY-001",
        source_transaction_id="BUY-001",
        source_acquisition_date=date(2026, 1, 1),
        retained_quantity=Decimal("75"),
        source_cost_local_before=Decimal("100"),
        source_cost_base_before=Decimal("75"),
        transferred_cost_local=Decimal("25"),
        transferred_cost_base=Decimal("18.75"),
        retained_cost_local=Decimal("75"),
        retained_cost_base=Decimal("56.25"),
        allocation_content_hash="",
    )
    identity_hash = canonical_content_hash(
        {
            "portfolio_id": "P1",
            "source_security_id": "BOND-1",
            "source_transaction_id": "DEMERGER-OUT-001",
        }
    )
    receipt_id = f"lot-basis-transfer:{identity_hash}"
    allocation = replace(
        allocation,
        allocation_content_hash=cost_basis_allocation_content_hash(
            receipt_id=receipt_id,
            payload=_allocation_payload(allocation),
        ),
    )
    receipt = LotBasisTransferReceiptReadRecord(
        receipt_id=receipt_id,
        receipt_version=1,
        source_transaction_id="DEMERGER-OUT-001",
        target_transaction_id="DEMERGER-IN-001",
        target_lot_id="LOT-DEMERGER-IN-001",
        portfolio_id="P1",
        source_instrument_id="BOND-1",
        source_security_id="BOND-1",
        target_instrument_id="EQUITY-1",
        transfer_timestamp=datetime(2026, 8, 4, tzinfo=UTC),
        transaction_type="DEMERGER_OUT",
        cost_basis_method="FIFO",
        calculation_policy_id="CORPORATE_ACTION_FIFO_POLICY",
        calculation_policy_version="1.0.0",
        status="ACTIVE",
        void_reason=None,
        transferred_cost_local=Decimal("25"),
        transferred_cost_base=Decimal("18.75"),
        allocation_count=1,
        semantic_content_hash="",
        previous_receipt_content_hash=None,
        receipt_content_hash="",
        transaction_calculation_lineage={"algorithm_id": "transaction-cost"},
        basis_transfer_calculation_lineage={"algorithm_id": "basis-transfer"},
    )
    semantic_hash = cost_basis_receipt_semantic_hash(
        _receipt_semantic_payload(receipt, [allocation])
    )
    return (
        replace(
            receipt,
            semantic_content_hash=semantic_hash,
            receipt_content_hash=receipt_version_content_hash(
                receipt_id=receipt_id,
                semantic_content_hash=semantic_hash,
                receipt_version=1,
                previous_receipt_content_hash=None,
            ),
        ),
        allocation,
    )


def _assert_corrupt(
    receipt: LotBasisTransferReceiptReadRecord,
    allocations: list[LotBasisTransferAllocationReadRecord],
    reason: str,
) -> None:
    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, allocations, predecessor_hash=None)

    assert reason in str(error.value.__cause__)
