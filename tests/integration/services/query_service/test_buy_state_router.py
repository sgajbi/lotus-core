from datetime import date
from decimal import Decimal
from unittest.mock import ANY, AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import PositionLotState

from src.services.query_service.app.dependencies import get_buy_state_service
from src.services.query_service.app.dtos.buy_state_dto import (
    AccruedIncomeOffsetRecord,
    AccruedIncomeOffsetsResponse,
    BuyCashLinkageResponse,
    PositionLotRecord,
    PositionLotsResponse,
)
from src.services.query_service.app.main import app
from src.services.query_service.app.services.buy_state_service import BuyStateService
from tests.test_support.tenant import TEST_TENANT_CONTEXT, TEST_TENANT_HEADERS

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_buy_state_service = MagicMock()
    mock_buy_state_service.get_position_lots = AsyncMock(
        return_value=PositionLotsResponse(
            portfolio_id="PORT-1",
            security_id="US0378331005",
            lots=[
                PositionLotRecord(
                    lot_id="LOT-TXN-1",
                    source_transaction_id="TXN-1",
                    portfolio_id="PORT-1",
                    instrument_id="AAPL",
                    security_id="US0378331005",
                    acquisition_date=date(2026, 2, 28),
                    original_quantity=100,
                    open_quantity=100,
                    lot_cost_local=15005.5,
                    lot_cost_base=15005.5,
                    accrued_interest_paid_local=0,
                )
            ],
        )
    )
    mock_buy_state_service.get_accrued_offsets = AsyncMock(
        return_value=AccruedIncomeOffsetsResponse(
            portfolio_id="PORT-1",
            security_id="US0378331005",
            offsets=[
                AccruedIncomeOffsetRecord(
                    offset_id="AIO-TXN-1",
                    source_transaction_id="TXN-1",
                    portfolio_id="PORT-1",
                    instrument_id="AAPL",
                    security_id="US0378331005",
                    accrued_interest_paid_local=1250,
                    remaining_offset_local=1250,
                )
            ],
        )
    )
    mock_buy_state_service.get_buy_cash_linkage = AsyncMock(
        return_value=BuyCashLinkageResponse(
            portfolio_id="PORT-1",
            transaction_id="TXN-1",
            transaction_type="BUY",
            economic_event_id="EVT-1",
            linked_transaction_group_id="LTG-1",
            calculation_policy_id="BUY_DEFAULT_POLICY",
            calculation_policy_version="1.0.0",
            cashflow_amount=-15005.5,
            cashflow_currency="USD",
            cashflow_classification="INVESTMENT_OUTFLOW",
        )
    )

    app.dependency_overrides[get_buy_state_service] = lambda: mock_buy_state_service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=TEST_TENANT_HEADERS,
    ) as client:
        yield client, mock_buy_state_service
    app.dependency_overrides.pop(get_buy_state_service, None)


async def test_get_position_lots_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/portfolios/PORT-1/positions/US0378331005/lots")
    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_id"] == "PORT-1"
    assert payload["lots"][0]["lot_id"] == "LOT-TXN-1"
    mock_service.get_position_lots.assert_awaited_once_with(
        portfolio_id="PORT-1",
        security_id="US0378331005",
        tenant_context=ANY,
    )
    forwarded = mock_service.get_position_lots.await_args.kwargs["tenant_context"]
    assert forwarded.tenant_id == TEST_TENANT_CONTEXT.tenant_id


@pytest.mark.parametrize(
    "quantity",
    [
        "100.0000000000",
        "0.1234567890",
        "0.0000000001",
        "12345678.1234567890",
        "99999999.9999999998",
        "99999999.9999999999",
        "0.0000000000",
    ],
)
async def test_registered_lots_preserve_exact_service_values(async_test_client, quantity):
    client, mock_service = async_test_client
    source = PositionLotState(
        lot_id="LOT-TXN-1",
        source_transaction_id="TXN-1",
        portfolio_id="PORT-1",
        instrument_id="AAPL",
        security_id="US0378331005",
        acquisition_date=date(2026, 2, 28),
        original_quantity=Decimal(quantity),
        open_quantity=Decimal(quantity),
        lot_cost_local=Decimal("15005.1234567890"),
        lot_cost_base=Decimal("17005.9876543210"),
        accrued_interest_paid_local=Decimal("0"),
        economic_event_id="EVT-1",
        linked_transaction_group_id="LTG-1",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        source_system="OMS_PRIMARY",
    )
    service = BuyStateService(AsyncMock())
    service.repo = AsyncMock()
    service.repo.portfolio_exists.return_value = True
    service.repo.get_position_lots.return_value = [source]
    mock_service.get_position_lots.side_effect = service.get_position_lots
    response = await client.get("/portfolios/PORT-1/positions/US0378331005/lots")
    assert response.status_code == 200
    lot = response.json()["lots"][0]
    for field in ("original_quantity", "open_quantity"):
        assert Decimal(str(lot[field])) == Decimal(quantity)
        assert isinstance(lot[field], str)
    for field in ("lot_cost_local", "lot_cost_base", "accrued_interest_paid_local"):
        assert Decimal(lot[field]) == getattr(source, field)
    for field in (
        "lot_id",
        "source_transaction_id",
        "economic_event_id",
        "linked_transaction_group_id",
        "calculation_policy_id",
        "calculation_policy_version",
        "source_system",
    ):
        assert lot[field] == getattr(source, field)
    # A supported consumer can parse the wire response directly back into exact Decimals.
    parsed = PositionLotsResponse.model_validate_json(response.content)
    assert parsed.lots[0].original_quantity == Decimal(quantity)
    assert parsed.lots[0].open_quantity == Decimal(quantity)


async def test_lot_quantity_openapi_matches_exact_wire_contract():
    schema = app.openapi()["components"]["schemas"]["PositionLotRecord"]["properties"]
    for field in ("original_quantity", "open_quantity"):
        assert schema[field]["type"] == "string"
        assert all(isinstance(example, str) for example in schema[field]["examples"])


async def test_get_accrued_offsets_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/portfolios/PORT-1/positions/US0378331005/accrued-offsets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["offsets"][0]["offset_id"] == "AIO-TXN-1"
    mock_service.get_accrued_offsets.assert_awaited_once_with(
        portfolio_id="PORT-1",
        security_id="US0378331005",
        tenant_context=ANY,
    )
    forwarded = mock_service.get_accrued_offsets.await_args.kwargs["tenant_context"]
    assert forwarded.tenant_id == TEST_TENANT_CONTEXT.tenant_id


async def test_get_cash_linkage_not_found(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_buy_cash_linkage.side_effect = LookupError(
        "BUY cash linkage not found for portfolio PORT-1 and transaction T404"
    )
    response = await client.get("/portfolios/PORT-1/transactions/T404/cash-linkage")
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "BUY cash linkage not found for portfolio PORT-1 and transaction T404"
    )


async def test_get_cash_linkage_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/portfolios/PORT-1/transactions/TXN-1/cash-linkage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["transaction_id"] == "TXN-1"
    assert payload["calculation_policy_id"] == "BUY_DEFAULT_POLICY"
    assert payload["cashflow_classification"] == "INVESTMENT_OUTFLOW"
    mock_service.get_buy_cash_linkage.assert_awaited_with(
        portfolio_id="PORT-1", transaction_id="TXN-1", tenant_context=ANY
    )
    forwarded = mock_service.get_buy_cash_linkage.await_args.kwargs["tenant_context"]
    assert forwarded.tenant_id == TEST_TENANT_CONTEXT.tenant_id


async def test_get_position_lots_not_found(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_lots.side_effect = LookupError("portfolio missing")
    response = await client.get("/portfolios/P404/positions/US0378331005/lots")
    assert response.status_code == 404
    assert "portfolio missing" in response.json()["detail"]


async def test_get_accrued_offsets_not_found(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_accrued_offsets.side_effect = LookupError("offsets missing")
    response = await client.get("/portfolios/P404/positions/US0378331005/accrued-offsets")
    assert response.status_code == 404
    assert "offsets missing" in response.json()["detail"]


async def test_get_position_lots_security_key_not_found_uses_investigative_404_example(
    async_test_client,
):
    client, mock_service = async_test_client
    mock_service.get_position_lots.side_effect = LookupError(
        "BUY state not found for portfolio PORT-1 and security SEC-MISSING"
    )

    response = await client.get("/portfolios/PORT-1/positions/SEC-MISSING/lots")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "BUY state not found for portfolio PORT-1 and security SEC-MISSING"
    )


async def test_get_accrued_offsets_security_key_not_found_uses_investigative_404_example(
    async_test_client,
):
    client, mock_service = async_test_client
    mock_service.get_accrued_offsets.side_effect = LookupError(
        "BUY state not found for portfolio PORT-1 and security SEC-MISSING"
    )

    response = await client.get("/portfolios/PORT-1/positions/SEC-MISSING/accrued-offsets")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "BUY state not found for portfolio PORT-1 and security SEC-MISSING"
    )
