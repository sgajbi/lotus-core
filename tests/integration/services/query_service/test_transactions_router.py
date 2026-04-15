from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.transaction_dto import (
    PaginatedTransactionResponse,
    TransactionCostRecord,
    TransactionRecord,
)
from src.services.query_service.app.dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
)
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_transaction_service = MagicMock()
    mock_transaction_service.get_transactions = AsyncMock(
        return_value=PaginatedTransactionResponse(
            portfolio_id="P1",
            total=1,
            skip=0,
            limit=10,
            transactions=[
                TransactionRecord(
                    transaction_id="T1",
                    transaction_date=datetime(2025, 8, 1, 0, 0, 0),
                    settlement_date=datetime(2025, 8, 3, 0, 0, 0),
                    transaction_type="INTEREST",
                    instrument_id="INST_1",
                    security_id="SEC_1",
                    quantity=0.0,
                    price=0.0,
                    gross_transaction_amount=125.0,
                    gross_cost=Decimal("125.00"),
                    trade_fee=Decimal("2.50"),
                    trade_currency="USD",
                    currency="USD",
                    costs=[
                        TransactionCostRecord(
                            fee_type="BROKERAGE",
                            amount=Decimal("2.50"),
                            currency="USD",
                        )
                    ],
                    cash_entry_mode="UPSTREAM_PROVIDED",
                    external_cash_transaction_id="CASH-ENTRY-2026-0001",
                    interest_direction="INCOME",
                    withholding_tax_amount=Decimal("10.00"),
                    other_interest_deductions_amount=Decimal("5.00"),
                    net_interest_amount=Decimal("110.00"),
                )
            ],
            **source_data_product_runtime_metadata(as_of_date=date(2025, 8, 1)),
        )
    )

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)

    with patch(
        "src.services.query_service.app.routers.transactions.TransactionService",
        return_value=mock_transaction_service,
    ):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_transaction_service

    app.dependency_overrides.pop(get_async_db_session, None)


async def test_get_transactions_success_with_sorting_and_filters(async_test_client):
    client, mock_service = async_test_client
    response = await client.get(
        "/portfolios/P1/transactions",
        params={
            "instrument_id": "INST_1",
            "security_id": "SEC_1",
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
            "skip": 5,
            "limit": 20,
            "sort_by": "transaction_date",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_id"] == "P1"
    assert payload["transactions"][0]["transaction_id"] == "T1"
    assert payload["transactions"][0]["settlement_date"] == "2025-08-03T00:00:00"
    assert payload["transactions"][0]["gross_cost"] == "125.00"
    assert payload["transactions"][0]["trade_fee"] == "2.50"
    assert payload["transactions"][0]["trade_currency"] == "USD"
    assert payload["transactions"][0]["costs"][0]["fee_type"] == "BROKERAGE"
    assert payload["transactions"][0]["cash_entry_mode"] == "UPSTREAM_PROVIDED"
    assert payload["transactions"][0]["external_cash_transaction_id"] == "CASH-ENTRY-2026-0001"
    assert payload["transactions"][0]["interest_direction"] == "INCOME"
    assert payload["transactions"][0]["withholding_tax_amount"] == "10.00"
    assert payload["transactions"][0]["other_interest_deductions_amount"] == "5.00"
    assert payload["transactions"][0]["net_interest_amount"] == "110.00"
    mock_service.get_transactions.assert_awaited_once_with(
        portfolio_id="P1",
        instrument_id="INST_1",
        security_id="SEC_1",
        transaction_type=None,
        component_type=None,
        linked_transaction_group_id=None,
        fx_contract_id=None,
        swap_event_id=None,
        near_leg_group_id=None,
        far_leg_group_id=None,
        start_date=datetime(2025, 8, 1, 0, 0).date(),
        end_date=datetime(2025, 8, 31, 0, 0).date(),
        as_of_date=None,
        include_projected=False,
        skip=5,
        limit=20,
        sort_by="transaction_date",
        sort_order="asc",
    )


async def test_get_transactions_unhandled_error_is_globally_mapped(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_transactions.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/transactions")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal Server Error"
    assert "correlation_id" in body


async def test_get_transactions_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_transactions.side_effect = ValueError("portfolio missing")

    response = await client.get("/portfolios/P404/transactions")

    assert response.status_code == 404
    assert "portfolio missing" in response.json()["detail"].lower()


async def test_get_transactions_forwards_as_of_and_include_projected(async_test_client):
    client, mock_service = async_test_client

    response = await client.get(
        "/portfolios/P1/transactions?as_of_date=2026-02-28&include_projected=true"
    )

    assert response.status_code == 200
    mock_service.get_transactions.assert_awaited_once_with(
        portfolio_id="P1",
        instrument_id=None,
        security_id=None,
        transaction_type=None,
        component_type=None,
        linked_transaction_group_id=None,
        fx_contract_id=None,
        swap_event_id=None,
        near_leg_group_id=None,
        far_leg_group_id=None,
        start_date=None,
        end_date=None,
        as_of_date=datetime(2026, 2, 28, 0, 0).date(),
        include_projected=True,
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="desc",
    )


async def test_get_transactions_for_security_drill_down_defaults_to_latest_first(
    async_test_client,
):
    client, mock_service = async_test_client

    response = await client.get("/portfolios/P1/transactions?security_id=SEC-HOLDING-1")

    assert response.status_code == 200
    mock_service.get_transactions.assert_awaited_once_with(
        portfolio_id="P1",
        instrument_id=None,
        security_id="SEC-HOLDING-1",
        transaction_type=None,
        component_type=None,
        linked_transaction_group_id=None,
        fx_contract_id=None,
        swap_event_id=None,
        near_leg_group_id=None,
        far_leg_group_id=None,
        start_date=None,
        end_date=None,
        as_of_date=None,
        include_projected=False,
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="desc",
    )


async def test_get_transactions_forwards_fx_filters(async_test_client):
    client, mock_service = async_test_client

    response = await client.get(
        "/portfolios/P1/transactions",
        params={
            "transaction_type": "FX_FORWARD",
            "component_type": "FX_CONTRACT_OPEN",
            "linked_transaction_group_id": "LTG-FX-2026-0001",
            "fx_contract_id": "FXC-LTG-FX-2026-0001",
            "swap_event_id": "FXSWAP-LTG-FX-2026-0001",
            "near_leg_group_id": "FXSWAP-LTG-FX-2026-0001-NEAR",
            "far_leg_group_id": "FXSWAP-LTG-FX-2026-0001-FAR",
        },
    )

    assert response.status_code == 200
    mock_service.get_transactions.assert_awaited_once_with(
        portfolio_id="P1",
        instrument_id=None,
        security_id=None,
        start_date=None,
        end_date=None,
        as_of_date=None,
        include_projected=False,
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="desc",
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        linked_transaction_group_id="LTG-FX-2026-0001",
        fx_contract_id="FXC-LTG-FX-2026-0001",
        swap_event_id="FXSWAP-LTG-FX-2026-0001",
        near_leg_group_id="FXSWAP-LTG-FX-2026-0001-NEAR",
        far_leg_group_id="FXSWAP-LTG-FX-2026-0001-FAR",
    )


async def test_get_transactions_preserves_settlement_date_for_trade_cash_and_income_shapes(
    async_test_client,
):
    client, mock_service = async_test_client
    mock_service.get_transactions.return_value = PaginatedTransactionResponse(
        portfolio_id="P1",
        total=3,
        skip=0,
        limit=10,
        transactions=[
            TransactionRecord(
                transaction_id="BUY-1",
                transaction_date=datetime(2025, 8, 1, 0, 0, 0),
                settlement_date=datetime(2025, 8, 3, 0, 0, 0),
                transaction_type="BUY",
                instrument_id="INST_BUY",
                security_id="SEC_BUY",
                quantity=10,
                price=100,
                gross_transaction_amount=1000,
                currency="USD",
            ),
            TransactionRecord(
                transaction_id="DEP-1",
                transaction_date=datetime(2025, 8, 2, 0, 0, 0),
                settlement_date=datetime(2025, 8, 2, 12, 0, 0),
                transaction_type="DEPOSIT",
                instrument_id="CASH_USD",
                security_id="CASH_USD",
                quantity=1,
                price=1,
                gross_transaction_amount=5000,
                currency="USD",
            ),
            TransactionRecord(
                transaction_id="INT-1",
                transaction_date=datetime(2025, 8, 4, 0, 0, 0),
                settlement_date=datetime(2025, 8, 5, 0, 0, 0),
                transaction_type="INTEREST",
                instrument_id="BOND_1",
                security_id="BOND_1",
                quantity=0,
                price=0,
                gross_transaction_amount=125,
                currency="USD",
            ),
        ],
        **source_data_product_runtime_metadata(as_of_date=date(2025, 8, 3)),
    )

    response = await client.get("/portfolios/P1/transactions")

    assert response.status_code == 200
    transactions = response.json()["transactions"]
    assert transactions[0]["settlement_date"] == "2025-08-03T00:00:00"
    assert transactions[1]["settlement_date"] == "2025-08-02T12:00:00"
    assert transactions[2]["settlement_date"] == "2025-08-05T00:00:00"
