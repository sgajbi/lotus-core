"""Verify admitted tenant authority reaches basis-transfer receipt resolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_service.app.routers.lot_basis_transfers import (
    get_latest_lot_basis_transfer_receipt,
)
from src.services.query_service.app.services.lot_basis_transfer_service import (
    LotBasisTransferService,
)
from tests.test_support.tenant import TEST_TENANT_CONTEXT


@pytest.mark.asyncio
async def test_basis_transfer_receipt_forwards_admitted_tenant() -> None:
    expected = object()
    service = MagicMock(spec=LotBasisTransferService)
    service.get_latest_receipt = AsyncMock(return_value=expected)
    request = SimpleNamespace(state=SimpleNamespace(tenant_context=TEST_TENANT_CONTEXT))

    result = await get_latest_lot_basis_transfer_receipt(
        request=request,
        portfolio_id="P1",
        source_transaction_id="DEMERGER-OUT-001",
        service=service,
    )

    assert result is expected
    service.get_latest_receipt.assert_awaited_once_with(
        tenant_context=TEST_TENANT_CONTEXT,
        portfolio_id="P1",
        source_transaction_id="DEMERGER-OUT-001",
    )
