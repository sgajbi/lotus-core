# tests/e2e/test_query_service_api.py

import pytest

from .api_client import E2EApiClient
from .data_factory import unique_suffix


@pytest.fixture(scope="module")
def setup_e2e_data(clean_db_module, e2e_api_client: E2EApiClient):
    """
    A module-scoped fixture to ingest a consistent set of data for testing
    API features like sorting, filtering, and pagination.
    """
    suffix = unique_suffix()
    portfolio_id = f"E2E_API_TEST_{suffix}"
    security_1 = f"S1_{suffix}"
    security_2 = f"S2_{suffix}"
    security_3 = f"S3_{suffix}"
    instrument_1 = f"A_{suffix}"
    instrument_2 = f"B_{suffix}"
    instrument_3 = f"C_{suffix}"

    # Ingest Portfolio
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": f"API_CIF_{suffix}",
                    "status": "ACTIVE",
                    "riskExposure": "a",
                    "investmentTimeHorizon": "b",
                    "portfolioType": "c",
                    "bookingCenter": "d",
                }
            ]
        },
    )

    # Ingest a diverse set of transactions for filtering and sorting
    transactions = [
        {
            "transaction_id": f"{portfolio_id}_T1",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_1,
            "security_id": security_1,
            "transaction_date": "2025-08-01T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 100,
            "gross_transaction_amount": 1000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_T2",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_2,
            "security_id": security_2,
            "transaction_date": "2025-08-05T11:00:00Z",
            "transaction_type": "BUY",
            "quantity": 5,
            "price": 200,
            "gross_transaction_amount": 1000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_T3",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_1,
            "security_id": security_1,
            "transaction_date": "2025-08-03T12:00:00Z",
            "transaction_type": "SELL",
            "quantity": 2,
            "price": 110,
            "gross_transaction_amount": 220,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_T4",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_3,
            "security_id": security_3,
            "transaction_date": "2025-08-05T09:00:00Z",
            "transaction_type": "BUY",
            "quantity": 25,
            "price": 50,
            "gross_transaction_amount": 1250,
            "trade_currency": "USD",
            "currency": "USD",
        },
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})

    # Poll until all transactions are available via the API
    poll_url = f"/portfolios/{portfolio_id}/transactions"

    def validation_func(data):
        return data.get("transactions") and {
            item["transaction_id"] for item in data["transactions"]
        } == {
            f"{portfolio_id}_T1",
            f"{portfolio_id}_T2",
            f"{portfolio_id}_T3",
            f"{portfolio_id}_T4",
        }

    e2e_api_client.poll_for_data(poll_url, validation_func, timeout=60)

    return {
        "portfolio_id": portfolio_id,
        "security_1": security_1,
    }


def test_transaction_query_default_sort(setup_e2e_data, e2e_api_client: E2EApiClient):
    """
    Tests that the default sort order for transactions is by date descending.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f"/portfolios/{portfolio_id}/transactions"

    response = e2e_api_client.query(url)
    data = response.json()

    assert len(data["transactions"]) == 4
    # Expected order: T2 (Aug 5 11:00), T4 (Aug 5 09:00), T3 (Aug 3), T1 (Aug 1)
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T2"
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T4"
    assert data["transactions"][2]["transaction_id"] == f"{portfolio_id}_T3"
    assert data["transactions"][3]["transaction_id"] == f"{portfolio_id}_T1"


def test_transaction_query_custom_sort(setup_e2e_data, e2e_api_client: E2EApiClient):
    """
    Tests sorting transactions by quantity in ascending order.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f"/portfolios/{portfolio_id}/transactions?sort_by=quantity&sort_order=asc"

    response = e2e_api_client.query(url)
    data = response.json()

    assert len(data["transactions"]) == 4
    # Expected order by quantity asc: T3 (2), T2 (5), T1 (10), T4 (25)
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T3"
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T2"
    assert data["transactions"][2]["transaction_id"] == f"{portfolio_id}_T1"
    assert data["transactions"][3]["transaction_id"] == f"{portfolio_id}_T4"


def test_transaction_query_filter_by_security_id(setup_e2e_data, e2e_api_client: E2EApiClient):
    """
    Tests filtering transactions by a specific security ID.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f"/portfolios/{portfolio_id}/transactions?security_id={setup_e2e_data['security_1']}"

    response = e2e_api_client.query(url)
    data = response.json()

    assert len(data["transactions"]) == 2
    assert data["total"] == 2

    # Verify both transactions for S1 are returned
    returned_ids = {t["transaction_id"] for t in data["transactions"]}
    assert f"{portfolio_id}_T1" in returned_ids
    assert f"{portfolio_id}_T3" in returned_ids


def test_transaction_query_filter_and_sort(setup_e2e_data, e2e_api_client: E2EApiClient):
    """
    Tests combining a filter (security_id) with custom sorting (quantity asc).
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = (
        f"/portfolios/{portfolio_id}/transactions"
        f"?security_id={setup_e2e_data['security_1']}&sort_by=quantity&sort_order=asc"
    )

    response = e2e_api_client.query(url)
    data = response.json()

    assert len(data["transactions"]) == 2
    # Expected order for S1 by quantity asc: T3 (2), T1 (10)
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T3"
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T1"


def test_transaction_query_pagination(setup_e2e_data, e2e_api_client: E2EApiClient):
    """
    Tests using limit and skip for paginating transaction results.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    base_url = f"/portfolios/{portfolio_id}/transactions"

    # ACT 1: Get the first page (limit=2, skip=0)
    url_page1 = f"{base_url}?limit=2&skip=0"
    response1 = e2e_api_client.query(url_page1)
    data1 = response1.json()

    # ASSERT 1
    assert data1["total"] == 4
    assert data1["skip"] == 0
    assert data1["limit"] == 2
    assert len(data1["transactions"]) == 2
    # Default sort is by date desc, so we expect the two latest transactions
    assert data1["transactions"][0]["transaction_id"] == f"{portfolio_id}_T2"
    assert data1["transactions"][1]["transaction_id"] == f"{portfolio_id}_T4"

    # ACT 2: Get the second page (limit=2, skip=2)
    url_page2 = f"{base_url}?limit=2&skip=2"
    response2 = e2e_api_client.query(url_page2)
    data2 = response2.json()

    # ASSERT 2
    assert data2["total"] == 4
    assert data2["skip"] == 2
    assert data2["limit"] == 2
    assert len(data2["transactions"]) == 2
    # We expect the next two transactions in the default sort order
    assert data2["transactions"][0]["transaction_id"] == f"{portfolio_id}_T3"
    assert data2["transactions"][1]["transaction_id"] == f"{portfolio_id}_T1"
