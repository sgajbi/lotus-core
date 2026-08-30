"""Verify the public lot-disposal supportability route and OpenAPI contract."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.dependencies import get_lot_disposal_service
from src.services.query_service.app.dtos.lot_disposal_dto import (
    LotDisposalAllocationResponse,
    LotDisposalReceiptResponse,
)
from src.services.query_service.app.main import app
from tests.test_support.tenant import TEST_TENANT_CONTEXT, TEST_TENANT_HEADERS

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
            allocations=[
                LotDisposalAllocationResponse(
                    allocation_ordinal=1,
                    source_lot_id="LOT-BUY-001",
                    source_transaction_id="BUY-001",
                    source_acquisition_date=date(2026, 1, 1),
                    consumed_quantity=Decimal("25"),
                    consumed_cost_local=Decimal("24.5"),
                    consumed_cost_base=Decimal("18.375"),
                    allocation_content_hash="c" * 64,
                    amortized_cost_profile_id="PROFILE-1",
                    amortized_cost_profile_version=1,
                    amortized_cost_profile_content_hash="d" * 64,
                    amortized_cost_currency="USD",
                    amortized_cost_recognized_through=date(2026, 8, 4),
                    amortized_cost_original_quantity=Decimal("100"),
                    amortized_cost_open_quantity_before=Decimal("25"),
                    amortized_cost_residual_quantity=Decimal("0"),
                    amortized_cost_scheduled_local=Decimal("25"),
                    amortized_cost_current_local=Decimal("24.5"),
                    amortized_cost_current_base=Decimal("18.375"),
                    amortized_cost_residual_local=Decimal("0"),
                    amortized_cost_book_fx_rate_to_base=Decimal("0.75"),
                    amortized_cost_residual_base=Decimal("0"),
                    amortized_cost_retained_rounding_local=Decimal("0.5"),
                    amortized_cost_retained_rounding_base=Decimal("0.375"),
                    amortized_cost_calculation_lineage={"algorithm_id": "amortized-cost"},
                )
            ],
        )
    )
    app.dependency_overrides[get_lot_disposal_service] = lambda: service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=TEST_TENANT_HEADERS,
    ) as client:
        yield client, service
    app.dependency_overrides.pop(get_lot_disposal_service, None)


async def test_get_latest_lot_disposal_receipt(client_and_service) -> None:
    client, service = client_and_service

    response = await client.get("/portfolios/P1/transactions/RED-001/lot-disposal-receipt")

    assert response.status_code == 200
    assert response.json()["transaction_type"] == "PARTIAL_REDEMPTION"
    allocation = response.json()["allocations"][0]
    assert allocation["amortized_cost_currency"] == "USD"
    assert allocation["amortized_cost_original_quantity"] == "100"
    assert allocation["amortized_cost_current_local"] == "24.5"
    assert allocation["amortized_cost_book_fx_rate_to_base"] == "0.75"
    assert allocation["amortized_cost_retained_rounding_base"] == "0.375"
    service.get_latest_receipt.assert_awaited_once()
    call = service.get_latest_receipt.await_args.kwargs
    assert call["portfolio_id"] == "P1"
    assert call["transaction_id"] == "RED-001"
    assert call["tenant_context"].tenant_id_text == TEST_TENANT_CONTEXT.tenant_id_text


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
    allocation_properties = response.json()["components"]["schemas"][
        "LotDisposalAllocationResponse"
    ]["properties"]
    assert {
        "amortized_cost_currency",
        "amortized_cost_original_quantity",
        "amortized_cost_open_quantity_before",
        "amortized_cost_residual_quantity",
        "amortized_cost_scheduled_local",
        "amortized_cost_current_local",
        "amortized_cost_current_base",
        "amortized_cost_residual_local",
        "amortized_cost_book_fx_rate_to_base",
        "amortized_cost_residual_base",
        "amortized_cost_retained_rounding_local",
        "amortized_cost_retained_rounding_base",
    } <= allocation_properties.keys()
