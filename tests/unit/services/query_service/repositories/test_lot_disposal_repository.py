"""Verify bounded, fail-closed latest-version lot-disposal receipt reads."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
)
from portfolio_common.domain.calculation_lineage import (
    build_calculation_lineage,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    cost_basis_allocation_content_hash,
    cost_basis_receipt_semantic_hash,
    receipt_version_content_hash,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.lot_disposal_records import (
    LotDisposalAllocationReadRecord,
    LotDisposalReceiptReadRecord,
)
from src.services.query_service.app.repositories.lot_disposal_repository import (
    CorruptLotDisposalReadModelError,
    LotDisposalRepository,
    _allocation_payload,
    _receipt_semantic_payload,
    _verify_receipt_integrity,
)


@pytest.mark.asyncio
async def test_latest_receipt_uses_one_scoped_verified_latest_version_query() -> None:
    receipt = MagicMock(receipt_id="RECEIPT-1", allocation_count=2)
    receipt.destination_type = "INTERNAL_LOT"
    receipt.target_transaction_id = "EXCHANGE-IN-001"
    receipt.target_lot_id = "LOT-EXCHANGE-IN-001"
    receipt.target_instrument_id = "BOND-2"
    receipt.external_destination_reference = None
    first = MagicMock(source_lot_id="LOT-1")
    second = MagicMock(source_lot_id="LOT-2")
    result = MagicMock()
    result.all.return_value = [(receipt, first, None), (receipt, second, None)]
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=result)

    with patch(
        "src.services.query_service.app.repositories.lot_disposal_repository."
        "_verify_receipt_integrity"
    ) as verify:
        resolved = await LotDisposalRepository(session).get_latest_receipt(
            portfolio_id="P1",
            transaction_id="RED-001",
        )

    assert resolved is not None
    mapped_receipt, mapped_allocations = resolved
    assert isinstance(mapped_receipt, LotDisposalReceiptReadRecord)
    assert mapped_receipt.receipt_id == "RECEIPT-1"
    assert mapped_receipt.allocation_count == 2
    assert mapped_receipt.destination_type == "INTERNAL_LOT"
    assert mapped_receipt.target_transaction_id == "EXCHANGE-IN-001"
    assert mapped_receipt.target_lot_id == "LOT-EXCHANGE-IN-001"
    assert all(isinstance(row, LotDisposalAllocationReadRecord) for row in mapped_allocations)
    assert [row.source_lot_id for row in mapped_allocations] == ["LOT-1", "LOT-2"]
    session.execute.assert_awaited_once()
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "LEFT OUTER JOIN lot_disposal_allocations" in compiled
    assert "LEFT OUTER JOIN lot_disposal_receipts AS" in compiled
    assert "max(lot_disposal_receipts.receipt_version)" in compiled
    assert "lot_disposal_receipts.portfolio_id = 'P1'" in compiled
    assert "lot_disposal_receipts.disposal_transaction_id = 'RED-001'" in compiled
    assert "ORDER BY lot_disposal_allocations.allocation_ordinal ASC" in compiled
    verify.assert_called_once_with(receipt, [first, second], predecessor_hash=None)


def test_integrity_accepts_complete_canonical_evidence() -> None:
    receipt, allocation = _valid_evidence()

    _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)


def test_integrity_fails_closed_on_missing_allocation_rows() -> None:
    receipt, _ = _valid_evidence()

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [], predecessor_hash=None)

    assert "allocation count mismatch" in str(error.value.__cause__)


def test_integrity_fails_closed_on_tampered_header() -> None:
    receipt, allocation = _valid_evidence()
    receipt.instrument_id = "TAMPERED-BOND"

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "semantic content hash mismatch" in str(error.value.__cause__)


def test_integrity_fails_closed_on_tampered_allocation_hash() -> None:
    receipt, allocation = _valid_evidence()
    allocation.allocation_content_hash = "0" * 64

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "allocation content hash mismatch" in str(error.value.__cause__)


def test_integrity_fails_closed_when_header_does_not_conserve_allocations() -> None:
    receipt, allocation = _valid_evidence()
    receipt.consumed_cost_local = Decimal("24.99")

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "economics do not reconcile" in str(error.value.__cause__)


def test_integrity_fails_closed_on_partial_amortized_cost_evidence() -> None:
    receipt, allocation = _valid_evidence()
    allocation.amortized_cost_profile_id = "PROFILE-1"

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "only partially persisted" in str(error.value.__cause__)


def test_integrity_verifies_immediate_predecessor_hash() -> None:
    receipt, allocation = _valid_evidence()
    predecessor_hash = "e" * 64
    receipt.receipt_version = 2
    receipt.previous_receipt_content_hash = predecessor_hash
    receipt.receipt_content_hash = receipt_version_content_hash(
        receipt_id=receipt.receipt_id,
        semantic_content_hash=receipt.semantic_content_hash,
        receipt_version=2,
        previous_receipt_content_hash=predecessor_hash,
    )
    allocation.receipt_version = 2

    _verify_receipt_integrity(receipt, [allocation], predecessor_hash=predecessor_hash)
    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash="f" * 64)

    assert "predecessor chain mismatch" in str(error.value.__cause__)


def _valid_evidence() -> tuple[LotDisposalReceiptRecord, LotDisposalAllocationRecord]:
    timestamp = datetime(2026, 8, 4, 10, 30, tzinfo=UTC)
    transaction_lineage = _lineage("transaction-cost", output={"cost": "100"})
    disposal_lineage = _lineage("lot-disposal", output={"quantity": "25"})
    identity_hash = canonical_content_hash(
        {
            "disposal_transaction_id": "EXCHANGE-OUT-001",
            "portfolio_id": "P1",
            "security_id": "BOND-1",
        }
    )
    receipt_id = f"lot-disposal:{identity_hash}"
    receipt = LotDisposalReceiptRecord(
        receipt_id=receipt_id,
        receipt_version=1,
        disposal_transaction_id="EXCHANGE-OUT-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        disposal_timestamp=timestamp,
        transaction_type="EXCHANGE_OUT",
        destination_type="INTERNAL_LOT",
        target_transaction_id="EXCHANGE-IN-001",
        target_lot_id="LOT-EXCHANGE-IN-001",
        target_instrument_id="BOND-2",
        external_destination_reference=None,
        cost_basis_method="FIFO",
        calculation_policy_id="CORPORATE_ACTION_FIFO_POLICY",
        calculation_policy_version="1.0.0",
        status="ACTIVE",
        void_reason=None,
        consumed_quantity=Decimal("25"),
        consumed_cost_local=Decimal("25"),
        consumed_cost_base=Decimal("18.75"),
        allocation_count=1,
        transaction_calculation_lineage=transaction_lineage,
        disposal_calculation_lineage=disposal_lineage,
        semantic_content_hash="",
        previous_receipt_content_hash=None,
        receipt_content_hash="",
    )
    allocation = LotDisposalAllocationRecord(
        receipt_id=receipt_id,
        receipt_version=1,
        portfolio_id="P1",
        security_id="BOND-1",
        allocation_ordinal=1,
        source_lot_id="LOT-BUY-001",
        source_transaction_id="BUY-001",
        source_acquisition_date=date(2026, 1, 1),
        consumed_quantity=Decimal("25"),
        consumed_cost_local=Decimal("25"),
        consumed_cost_base=Decimal("18.75"),
        allocation_content_hash="",
    )
    allocation.allocation_content_hash = cost_basis_allocation_content_hash(
        receipt_id=receipt_id,
        payload=_allocation_payload(receipt, allocation),
    )
    receipt.semantic_content_hash = cost_basis_receipt_semantic_hash(
        _receipt_semantic_payload(receipt, [allocation])
    )
    receipt.receipt_content_hash = receipt_version_content_hash(
        receipt_id=receipt_id,
        semantic_content_hash=receipt.semantic_content_hash,
        receipt_version=1,
        previous_receipt_content_hash=None,
    )
    return receipt, allocation


def _lineage(algorithm_id: str, *, output: dict[str, object]) -> dict[str, object]:
    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"source": algorithm_id},
        output_payload=output,
    ).lineage_payload()
