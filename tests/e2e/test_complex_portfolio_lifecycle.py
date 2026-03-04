import uuid

import pytest

from .api_client import E2EApiClient


@pytest.fixture(scope="module")
def setup_complex_lifecycle_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    Creates a realistic cross-service lifecycle:
    - mixed activity types (deposit, buy/sell, dividend, fee)
    - multi-currency instrument with FX rates containing gaps
    - full pipeline validation through summary/review/support APIs
    """
    portfolio_id = f"E2E_COMPLEX_{uuid.uuid4().hex[:8].upper()}"
    as_of_date = "2025-09-05"
    security_id = "SEC_SAP_EU"
    cash_security_id = "CASH_USD"

    portfolio_payload = {
        "portfolios": [
            {
                "portfolio_id": portfolio_id,
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "risk_exposure": "Moderate",
                "investment_time_horizon": "Long",
                "portfolio_type": "Discretionary",
                "booking_center_code": "SG",
                "client_id": "E2E_COMPLEX_CIF",
                "status": "ACTIVE",
            }
        ]
    }
    instruments_payload = {
        "instruments": [
            {
                "security_id": cash_security_id,
                "name": "US Dollar Cash",
                "isin": "CASH_USD_E2E_COMPLEX",
                "currency": "USD",
                "product_type": "Cash",
                "asset_class": "Cash",
            },
            {
                "security_id": security_id,
                "name": "SAP SE",
                "isin": "DE0007164600",
                "currency": "EUR",
                "product_type": "Equity",
                "asset_class": "Equity",
                "sector": "Technology",
                "country_of_risk": "DE",
            },
        ]
    }
    business_dates_payload = {
        "business_dates": [
            {"business_date": "2025-09-01"},
            {"business_date": "2025-09-02"},
            {"business_date": "2025-09-03"},
            {"business_date": "2025-09-04"},
            {"business_date": as_of_date},
        ]
    }
    transactions_payload = {
        "transactions": [
            {
                "transaction_id": f"{portfolio_id}_DEP_01",
                "portfolio_id": portfolio_id,
                "instrument_id": "CASH",
                "security_id": cash_security_id,
                "transaction_date": "2025-09-01T09:00:00Z",
                "transaction_type": "DEPOSIT",
                "quantity": 300000,
                "price": 1,
                "gross_transaction_amount": 300000,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": f"{portfolio_id}_BUY_SAP",
                "portfolio_id": portfolio_id,
                "instrument_id": "SAP",
                "security_id": security_id,
                "transaction_date": "2025-09-01T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1000,
                "price": 100,
                "gross_transaction_amount": 100000,
                "trade_currency": "EUR",
                "currency": "EUR",
            },
            {
                "transaction_id": f"{portfolio_id}_CASH_OUT_BUY",
                "portfolio_id": portfolio_id,
                "instrument_id": "CASH",
                "security_id": cash_security_id,
                "transaction_date": "2025-09-01T10:00:00Z",
                "transaction_type": "SELL",
                "quantity": 110000,
                "price": 1,
                "gross_transaction_amount": 110000,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": f"{portfolio_id}_DIV_SAP",
                "portfolio_id": portfolio_id,
                "instrument_id": "SAP",
                "security_id": security_id,
                "transaction_date": "2025-09-03T10:00:00Z",
                "transaction_type": "DIVIDEND",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 1000,
                "trade_currency": "EUR",
                "currency": "EUR",
            },
            {
                "transaction_id": f"{portfolio_id}_CASH_IN_DIV",
                "portfolio_id": portfolio_id,
                "instrument_id": "CASH",
                "security_id": cash_security_id,
                "transaction_date": "2025-09-03T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1120,
                "price": 1,
                "gross_transaction_amount": 1120,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": f"{portfolio_id}_FEE",
                "portfolio_id": portfolio_id,
                "instrument_id": "CASH",
                "security_id": cash_security_id,
                "transaction_date": "2025-09-04T10:00:00Z",
                "transaction_type": "FEE",
                "quantity": 1,
                "price": 120,
                "gross_transaction_amount": 120,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": f"{portfolio_id}_SELL_SAP",
                "portfolio_id": portfolio_id,
                "instrument_id": "SAP",
                "security_id": security_id,
                "transaction_date": "2025-09-05T10:00:00Z",
                "transaction_type": "SELL",
                "quantity": 200,
                "price": 108,
                "gross_transaction_amount": 21600,
                "trade_currency": "EUR",
                "currency": "EUR",
            },
            {
                "transaction_id": f"{portfolio_id}_CASH_IN_SELL",
                "portfolio_id": portfolio_id,
                "instrument_id": "CASH",
                "security_id": cash_security_id,
                "transaction_date": "2025-09-05T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 24840,
                "price": 1,
                "gross_transaction_amount": 24840,
                "trade_currency": "USD",
                "currency": "USD",
            },
        ]
    }
    market_prices_payload = {
        "market_prices": [
            {"security_id": security_id, "price_date": as_of_date, "price": 112, "currency": "EUR"},
            {
                "security_id": cash_security_id,
                "price_date": as_of_date,
                "price": 1,
                "currency": "USD",
            },
        ]
    }
    fx_rates_payload = {
        "fx_rates": [
            {"from_currency": "EUR", "to_currency": "USD", "rate_date": "2025-09-01", "rate": 1.10},
            {"from_currency": "EUR", "to_currency": "USD", "rate_date": "2025-09-03", "rate": 1.12},
            {"from_currency": "EUR", "to_currency": "USD", "rate_date": "2025-09-05", "rate": 1.15},
        ]
    }

    assert e2e_api_client.ingest("/ingest/portfolios", portfolio_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/instruments", instruments_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/business-dates", business_dates_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/fx-rates", fx_rates_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/transactions", transactions_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/market-prices", market_prices_payload).status_code == 202

    poll_db_until(
        query="""
            SELECT valuation_status
            FROM daily_position_snapshots
            WHERE portfolio_id = :pid AND date = :dt AND security_id = :sid
        """,
        params={"pid": portfolio_id, "dt": as_of_date, "sid": security_id},
        validation_func=lambda r: r is not None and r.valuation_status == "VALUED_CURRENT",
        timeout=300,
        fail_message="Complex lifecycle positions were not valued for final as_of_date.",
    )

    return {
        "portfolio_id": portfolio_id,
        "as_of_date": as_of_date,
        "security_id": security_id,
    }


def test_complex_lifecycle_cross_api_consistency(
    setup_complex_lifecycle_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_complex_lifecycle_data["portfolio_id"]
    as_of_date = setup_complex_lifecycle_data["as_of_date"]
    security_id = setup_complex_lifecycle_data["security_id"]

    summary_response = e2e_api_client.post_query(
        f"/portfolios/{portfolio_id}/summary",
        {
            "as_of_date": as_of_date,
            "period": {"type": "EXPLICIT", "from": "2025-09-01", "to": as_of_date},
            "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY", "ALLOCATION"],
            "allocation_dimensions": ["ASSET_CLASS", "CURRENCY", "SECTOR"],
        },
        raise_for_status=False,
    )
    assert summary_response.status_code in {404, 410}
    if summary_response.status_code == 410:
        summary = summary_response.json()["detail"]
        assert summary["code"] == "LOTUS_CORE_LEGACY_ENDPOINT_REMOVED"
        assert summary["target_service"] == "lotus-report"

    review_response = e2e_api_client.post_query(
        f"/portfolios/{portfolio_id}/review",
        {
            "as_of_date": as_of_date,
            "sections": [
                "OVERVIEW",
                "ALLOCATION",
                "PERFORMANCE",
                "RISK_ANALYTICS",
                "INCOME_AND_ACTIVITY",
                "HOLDINGS",
                "TRANSACTIONS",
            ],
        },
        raise_for_status=False,
    )
    assert review_response.status_code in {404, 410}
    if review_response.status_code == 410:
        review = review_response.json()["detail"]
        assert review["code"] == "LOTUS_CORE_LEGACY_ENDPOINT_REMOVED"
        assert review["target_service"] == "lotus-report"

    support_response = e2e_api_client.query(f"/support/portfolios/{portfolio_id}/overview")
    support_data = support_response.json()
    assert support_response.status_code == 200
    assert support_data["portfolio_id"] == portfolio_id
    assert isinstance(support_data["pending_valuation_jobs"], int)
    assert isinstance(support_data["pending_aggregation_jobs"], int)

    lineage_response = e2e_api_client.query(
        f"/lineage/portfolios/{portfolio_id}/securities/{security_id}"
    )
    lineage_data = lineage_response.json()
    assert lineage_response.status_code == 200
    assert lineage_data["portfolio_id"] == portfolio_id
    assert lineage_data["security_id"] == security_id
    assert lineage_data["epoch"] >= 0


def test_complex_lifecycle_positions_contract(
    setup_complex_lifecycle_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_complex_lifecycle_data["portfolio_id"]

    response = e2e_api_client.query(f"/portfolios/{portfolio_id}/positions")
    data = response.json()
    assert response.status_code == 200
    assert data["portfolio_id"] == portfolio_id
    assert len(data["positions"]) >= 1

    for position in data["positions"]:
        assert "security_id" in position
        assert "isin" in position
        assert "currency" in position
        assert "weight" in position
