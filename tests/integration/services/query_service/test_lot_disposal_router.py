"""Verify the public lot-disposal supportability route and OpenAPI contract."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.dependencies import get_lot_disposal_service
from src.services.query_service.app.dtos.lot_disposal_dto import LotDisposalReceiptResponse
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client_and_service():
    service = MagicMock()
    service.get_latest_receipt = AsyncMock(
        return_value=LotDisposalReceiptResponse(
            receipt_id="lot-disposal:abc",
            receipt_version=1,
            disposal_transaction_id="RED-001",
            portfolio_id="P1",
            instrument_id="BOND-1",
            security_id="BOND-1",
            disposal_timestamp=datetime(2026, 8, 4, tzinfo=UTC),
            transaction_type="PARTIAL_REDEMPTION",
            cost_basis_method="FIFO",
            status="ACTIVE",
            consumed_quantity=Decimal("25"),
            consumed_cost_local=Decimal("24.5"),
            consumed_cost_base=Decimal("18.375"),
            semantic_content_hash="a" * 64,
            receipt_content_hash="b" * 64,
            transaction_calculation_lineage={"algorithm_id": "transaction-cost"},
            allocations=[],
        )
    )
    app.dependency_overrides[get_lot_disposal_service] = lambda: service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, service
    app.dependency_overrides.pop(get_lot_disposal_service, None)


async def test_get_latest_lot_disposal_receipt(client_and_service) -> None:
    client, service = client_and_service

    response = await client.get("/portfolios/P1/transactions/RED-001/lot-disposal-receipt")

    assert response.status_code == 200
    assert response.json()["transaction_type"] == "PARTIAL_REDEMPTION"
    service.get_latest_receipt.assert_awaited_once_with(
        portfolio_id="P1",
        transaction_id="RED-001",
    )


async def test_lot_disposal_receipt_not_found_maps_to_404(client_and_service) -> None:
    client, service = client_and_service
    service.get_latest_receipt.side_effect = LookupError("receipt missing")

    response = await client.get("/portfolios/P1/transactions/RED-404/lot-disposal-receipt")

    assert response.status_code == 404
    assert response.json()["detail"] == "receipt missing"


async def test_openapi_documents_transaction_neutral_receipt(client_and_service) -> None:
    client, _ = client_and_service
    response = await client.get("/openapi.json")

    operation = response.json()["paths"][
        "/portfolios/{portfolio_id}/transactions/{transaction_id}/lot-disposal-receipt"
    ]["get"]
    assert operation["tags"] == ["Lot Disposal Receipts"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "LotDisposalReceiptResponse"
    )
