"""Verify bounded latest-version lot-disposal receipt queries."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.lot_disposal_repository import (
    LotDisposalRepository,
)


@pytest.mark.asyncio
async def test_latest_receipt_uses_one_scoped_latest_version_query() -> None:
    receipt = MagicMock()
    first = MagicMock()
    second = MagicMock()
    result = MagicMock()
    result.all.return_value = [(receipt, first), (receipt, second)]
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=result)

    resolved = await LotDisposalRepository(session).get_latest_receipt(
        portfolio_id="P1",
        transaction_id="RED-001",
    )

    assert resolved == (receipt, [first, second])
    session.execute.assert_awaited_once()
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "LEFT OUTER JOIN lot_disposal_allocations" in compiled
    assert "max(lot_disposal_receipts.receipt_version)" in compiled
    assert "lot_disposal_receipts.portfolio_id = 'P1'" in compiled
    assert "lot_disposal_receipts.disposal_transaction_id = 'RED-001'" in compiled
    assert "ORDER BY lot_disposal_allocations.allocation_ordinal ASC" in compiled
