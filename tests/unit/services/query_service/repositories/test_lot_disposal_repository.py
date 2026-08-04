"""Verify bounded latest-version lot-disposal receipt queries."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.lot_disposal_records import (
    LotDisposalAllocationReadRecord,
    LotDisposalReceiptReadRecord,
)
from src.services.query_service.app.repositories.lot_disposal_repository import (
    LotDisposalRepository,
)


@pytest.mark.asyncio
async def test_latest_receipt_uses_one_scoped_latest_version_query() -> None:
    receipt = MagicMock()
    receipt.receipt_id = "RECEIPT-1"
    receipt.destination_type = "INTERNAL_LOT"
    receipt.target_transaction_id = "EXCHANGE-IN-001"
    receipt.target_lot_id = "LOT-EXCHANGE-IN-001"
    receipt.target_instrument_id = "BOND-2"
    receipt.external_destination_reference = None
    first = MagicMock()
    first.source_lot_id = "LOT-1"
    second = MagicMock()
    second.source_lot_id = "LOT-2"
    result = MagicMock()
    result.all.return_value = [(receipt, first), (receipt, second)]
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=result)

    resolved = await LotDisposalRepository(session).get_latest_receipt(
        portfolio_id="P1",
        transaction_id="RED-001",
    )

    assert resolved is not None
    mapped_receipt, mapped_allocations = resolved
    assert isinstance(mapped_receipt, LotDisposalReceiptReadRecord)
    assert mapped_receipt.receipt_id == "RECEIPT-1"
    assert mapped_receipt.destination_type == "INTERNAL_LOT"
    assert mapped_receipt.target_transaction_id == "EXCHANGE-IN-001"
    assert mapped_receipt.target_lot_id == "LOT-EXCHANGE-IN-001"
    assert all(isinstance(row, LotDisposalAllocationReadRecord) for row in mapped_allocations)
    assert [row.source_lot_id for row in mapped_allocations] == ["LOT-1", "LOT-2"]
    session.execute.assert_awaited_once()
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "LEFT OUTER JOIN lot_disposal_allocations" in compiled
    assert "max(lot_disposal_receipts.receipt_version)" in compiled
    assert "lot_disposal_receipts.portfolio_id = 'P1'" in compiled
    assert "lot_disposal_receipts.disposal_transaction_id = 'RED-001'" in compiled
    assert "ORDER BY lot_disposal_allocations.allocation_ordinal ASC" in compiled
