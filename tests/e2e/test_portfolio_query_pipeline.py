# tests/e2e/test_portfolio_query_pipeline.py

import pytest
import requests

from .api_client import E2EApiClient
from .data_factory import unique_suffix


@pytest.fixture(scope="module")
def setup_portfolio_data(clean_db_module, e2e_api_client: E2EApiClient):
    """
    A module-scoped fixture that ingests a set of portfolios,
    and waits for them to be available via the query API.
    """
    suffix = unique_suffix()
    portfolio_1 = f"E2E_QUERY_{suffix}_01"
    portfolio_2 = f"E2E_QUERY_{suffix}_02"
    portfolio_3 = f"E2E_QUERY_{suffix}_03"
    client_100 = f"CIF_{suffix}_100"
    client_200 = f"CIF_{suffix}_200"
    booking_center_sg = f"SG_{suffix}"
    booking_center_ch = f"CH_{suffix}"
    payload = {
        "portfolios": [
            {
                "portfolioId": portfolio_1,
                "baseCurrency": "USD",
                "openDate": "2024-01-01",
                "riskExposure": "High",
                "investmentTimeHorizon": "Long",
                "portfolioType": "Discretionary",
                "bookingCenter": booking_center_sg,
                "cifId": client_100,
                "status": "Active",
            },
            {
                "portfolioId": portfolio_2,
                "baseCurrency": "CHF",
                "openDate": "2024-02-01",
                "riskExposure": "Medium",
                "investmentTimeHorizon": "Medium",
                "portfolioType": "Advisory",
                "bookingCenter": booking_center_sg,
                "cifId": client_100,
                "status": "Active",
            },
            {
                "portfolioId": portfolio_3,
                "baseCurrency": "EUR",
                "openDate": "2024-03-01",
                "riskExposure": "Low",
                "investmentTimeHorizon": "Short",
                "portfolioType": "Execution-only",
                "bookingCenter": booking_center_ch,
                "cifId": client_200,
                "status": "Closed",
            },
        ]
    }

    e2e_api_client.ingest("/ingest/portfolios", payload)

    # Poll to ensure all data is persisted before running tests
    e2e_api_client.poll_for_data(
        f"/portfolios?client_id={client_100}",
        lambda data: data.get("portfolios")
        and {row["portfolio_id"] for row in data["portfolios"]} == {portfolio_1, portfolio_2},
        timeout=60,
    )
    e2e_api_client.poll_for_data(
        f"/portfolios?portfolio_id={portfolio_3}",
        lambda data: data.get("portfolios")
        and len(data["portfolios"]) == 1
        and data["portfolios"][0]["portfolio_id"] == portfolio_3,
        timeout=60,
    )

    return {
        "portfolio_1": portfolio_1,
        "portfolio_2": portfolio_2,
        "portfolio_3": portfolio_3,
        "client_100": client_100,
        "booking_center_ch": booking_center_ch,
    }


def test_query_by_portfolio_id(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests fetching a single portfolio by its unique ID."""
    response = e2e_api_client.query(
        f"/portfolios?portfolio_id={setup_portfolio_data['portfolio_1']}"
    )
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == setup_portfolio_data["portfolio_1"]
    assert data["portfolios"][0]["base_currency"] == "USD"


def test_query_by_cif_id(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests fetching all portfolios belonging to a specific client (CIF ID)."""
    response = e2e_api_client.query(
        f"/portfolios?client_id={setup_portfolio_data['client_100']}"
    )
    data = response.json()

    assert len(data["portfolios"]) == 2
    portfolio_ids = {p["portfolio_id"] for p in data["portfolios"]}
    assert portfolio_ids == {
        setup_portfolio_data["portfolio_1"],
        setup_portfolio_data["portfolio_2"],
    }


def test_query_by_booking_center(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests fetching all portfolios from a specific booking center."""
    response = e2e_api_client.query(
        f"/portfolios?booking_center_code={setup_portfolio_data['booking_center_ch']}"
    )
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == setup_portfolio_data["portfolio_3"]
    assert data["portfolios"][0]["status"] == "Closed"


def test_query_no_filters(setup_portfolio_data, e2e_api_client: E2EApiClient):
    """Tests that fetching with no filters returns all portfolios."""
    response = e2e_api_client.query("/portfolios")
    data = response.json()

    returned_ids = {row["portfolio_id"] for row in data["portfolios"]}
    assert {
        setup_portfolio_data["portfolio_1"],
        setup_portfolio_data["portfolio_2"],
        setup_portfolio_data["portfolio_3"],
    }.issubset(returned_ids)


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
