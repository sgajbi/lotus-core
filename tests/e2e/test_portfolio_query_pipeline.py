# tests/e2e/test_portfolio_query_pipeline.py
import pytest
import requests

from .api_client import E2EApiClient


@pytest.fixture(scope="module")
def setup_portfolio_data(clean_db_module, e2e_api_client: E2EApiClient):
    """
    A module-scoped fixture that ingests a set of portfolios,
    and waits for them to be available via the query API.
    """
    payload = {
        "portfolios": [
            {
                "portfolioId": "E2E_QUERY_01",
                "baseCurrency": "USD",
                "openDate": "2024-01-01",
                "riskExposure": "High",
                "investmentTimeHorizon": "Long",
                "portfolioType": "Discretionary",
                "bookingCenter": "Singapore",
                "cifId": "CIF_100",
                "status": "Active",
            },
            {
                "portfolioId": "E2E_QUERY_02",
                "baseCurrency": "CHF",
                "openDate": "2024-02-01",
                "riskExposure": "Medium",
                "investmentTimeHorizon": "Medium",
                "portfolioType": "Advisory",
                "bookingCenter": "Singapore",
                "cifId": "CIF_100",
                "status": "Active",
            },
            {
                "portfolioId": "E2E_QUERY_03",
                "baseCurrency": "EUR",
                "openDate": "2024-03-01",
                "riskExposure": "Low",
                "investmentTimeHorizon": "Short",
                "portfolioType": "Execution-only",
                "bookingCenter": "Zurich",
                "cifId": "CIF_200",
                "status": "Closed",
            },
        ]
    }

    e2e_api_client.ingest("/ingest/portfolios", payload)

    # Poll to ensure all data is persisted before running tests
    e2e_api_client.poll_for_data(
        "/portfolios",
        lambda data: data.get("portfolios") and len(data["portfolios"]) >= 3,
        timeout=60,
    )


def test_query_by_portfolio_id(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests fetching a single portfolio by its unique ID."""
    response = e2e_api_client.query("/portfolios?portfolio_id=E2E_QUERY_01")
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == "E2E_QUERY_01"
    assert data["portfolios"][0]["base_currency"] == "USD"


def test_query_by_cif_id(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests fetching all portfolios belonging to a specific client (CIF ID)."""
    response = e2e_api_client.query("/portfolios?client_id=CIF_100")
    data = response.json()

    assert len(data["portfolios"]) == 2
    portfolio_ids = {p["portfolio_id"] for p in data["portfolios"]}
    assert "E2E_QUERY_01" in portfolio_ids
    assert "E2E_QUERY_02" in portfolio_ids


def test_query_by_booking_center(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests fetching all portfolios from a specific booking center."""
    response = e2e_api_client.query("/portfolios?booking_center_code=Zurich")
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == "E2E_QUERY_03"
    assert data["portfolios"][0]["status"] == "Closed"


def test_query_no_filters(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests that fetching with no filters returns all portfolios."""
    response = e2e_api_client.query("/portfolios")
    data = response.json()

    assert len(data["portfolios"]) >= 3


def test_query_by_non_existent_portfolio_id_returns_404(
    setup_portfolio_data, e2e_api_client: E2EApiClient
):
    """
    Tests that querying for a specific but non-existent portfolio ID returns a 404 Not Found.
    """
    non_existent_id = "PORT_DOES_NOT_EXIST"
    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        e2e_api_client.query(f"/portfolios/{non_existent_id}")

    assert excinfo.value.response.status_code == 404
    assert excinfo.value.response.json() == {
        "detail": f"Portfolio with id {non_existent_id} not found"
    }
