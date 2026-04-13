# tests/e2e/test_analytics_input_money_weighted_returns_pipeline.py
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from .api_client import E2EApiClient
from .assertions import as_decimal, assert_legacy_endpoint_status


@pytest.fixture(scope="module")
def setup_mwr_data(clean_db_module, db_engine, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture to ingest data for an MWR scenario and wait for the
    backend pipeline to generate the necessary time-series data using a robust
    sequential ingestion pattern.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_MWR_PERF_{suffix}"
    cash_security_id = f"CASH_USD_{suffix}"
    transaction_ids = {
        "deposit_1": f"{portfolio_id}_DEPOSIT_01",
        "deposit_2": f"{portfolio_id}_DEPOSIT_02",
        "fee": f"{portfolio_id}_FEE_01",
        "tax": f"{portfolio_id}_TAX_01",
        "withdrawal": f"{portfolio_id}_WITHDRAWAL_01",
    }

    # --- Ingest Prerequisite Data ---
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2025-01-01",
                    "client_id": f"MWR_CIF_{suffix}",
                    "status": "ACTIVE",
                    "risk_exposure": "a",
                    "investment_time_horizon": "b",
                    "portfolio_type": "c",
                    "booking_center_code": "d",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": cash_security_id,
                    "name": "US Dollar",
                    "isin": f"CASH_USD_ISIN_{suffix}",
                    "currency": "USD",
                    "product_type": "Cash",
                }
            ]
        },
    )

    # Ingest all business dates up front to ensure schedulers can work
    all_dates = []
    current_date = date(2025, 8, 1)
    while current_date <= date(2025, 8, 31):
        all_dates.append({"business_date": current_date.isoformat()})
        current_date += timedelta(days=1)
    if all_dates:
        e2e_api_client.ingest("/ingest/business-dates", {"business_dates": all_dates})

    # --- Ingest transactions and prices ---
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": transaction_ids["deposit_1"],
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-01T10:00:00Z",
                    "transaction_type": "DEPOSIT",
                    "quantity": 1000,
                    "price": 1,
                    "gross_transaction_amount": 1000,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": transaction_ids["deposit_2"],
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-15T10:00:00Z",
                    "transaction_type": "DEPOSIT",
                    "quantity": 200,
                    "price": 1,
                    "gross_transaction_amount": 200,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": transaction_ids["fee"],
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-16T10:00:00Z",
                    "transaction_type": "FEE",
                    "quantity": 1,
                    "price": 25,
                    "gross_transaction_amount": 25,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": transaction_ids["tax"],
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-17T10:00:00Z",
                    "transaction_type": "TAX",
                    "quantity": 1,
                    "price": 10,
                    "gross_transaction_amount": 10,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": transaction_ids["withdrawal"],
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-18T10:00:00Z",
                    "transaction_type": "WITHDRAWAL",
                    "quantity": 100,
                    "price": 1,
                    "gross_transaction_amount": 100,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {
                    "security_id": cash_security_id,
                    "price_date": "2025-08-01",
                    "price": 1.0,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2025-08-15",
                    "price": 1.0,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2025-08-16",
                    "price": 1.0,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2025-08-17",
                    "price": 1.0,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2025-08-18",
                    "price": 1.0,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2025-08-31",
                    "price": 1.0,
                    "currency": "USD",
                },
            ]
        },
    )

    # Wait for the full downstream portfolio-timeseries chain to settle for the
    # final business date. This module seeds a month-long scenario, so only
    # waiting for transaction persistence leaves legitimate aggregation backlog
    # running into the next module.
    poll_db_until(
        query=(
            "SELECT eod_market_value FROM portfolio_timeseries "
            "WHERE portfolio_id = :pid AND date = :date"
        ),
        params={"pid": portfolio_id, "date": "2025-08-31"},
        validation_func=lambda r: r is not None,
        timeout=180,
        fail_message="Pipeline did not settle MWR portfolio timeseries through the final day.",
    )

    return {
        "portfolio_id": portfolio_id,
        "cash_security_id": cash_security_id,
        "transaction_ids": transaction_ids,
    }


def test_analytics_input_mwr_contract_dataset_is_queryable(
    setup_mwr_data, e2e_api_client: E2EApiClient
):
    """
    Verifies lotus-core MWR endpoint is hard-disabled and callers are expected
    to use lotus-performance for analytics calculations.
    """
    # ARRANGE
    portfolio_id = setup_mwr_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/performance/mwr"

    request_payload = {
        "scope": {"as_of_date": "2025-08-31"},
        "periods": [
            {"type": "EXPLICIT", "name": "TestPeriod", "from": "2025-08-01", "to": "2025-08-31"}
        ],
        "options": {"annualize": True},
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)
    assert_legacy_endpoint_status(response)


@pytest.mark.parametrize(
    ("as_of_date", "expected_quantity", "expected_market_value"),
    [
        ("2025-08-01", Decimal("1000"), Decimal("1000")),
        ("2025-08-15", Decimal("1200"), Decimal("1200")),
        ("2025-08-16", Decimal("1175"), Decimal("1175")),
        ("2025-08-17", Decimal("1165"), Decimal("1165")),
        ("2025-08-18", Decimal("1065"), Decimal("1065")),
    ],
)
def test_cash_portfolio_flows_pipeline_persists_non_zero_positions_and_analytics(
    setup_mwr_data,
    e2e_api_client: E2EApiClient,
    as_of_date: str,
    expected_quantity: Decimal,
    expected_market_value: Decimal,
):
    portfolio_id = setup_mwr_data["portfolio_id"]

    positions_response = e2e_api_client.query(
        f"/portfolios/{portfolio_id}/positions?as_of_date={as_of_date}"
    )
    positions_payload = positions_response.json()
    assert len(positions_payload["positions"]) == 1
    cash_position = positions_payload["positions"][0]
    assert cash_position["security_id"] == setup_mwr_data["cash_security_id"]
    assert as_decimal(cash_position["quantity"]) == expected_quantity
    assert as_decimal(cash_position["valuation"]["market_value"]) == expected_market_value


def test_cash_portfolio_flows_pipeline_persists_cashflows_and_timeseries(
    setup_mwr_data, db_engine
):
    portfolio_id = setup_mwr_data["portfolio_id"]

    with Session(db_engine) as session:
        cashflows = session.execute(
            text(
                """
                select distinct on (transaction_id)
                    transaction_id, amount, classification, timing, epoch
                from cashflows
                where portfolio_id = :portfolio_id
                order by transaction_id, epoch desc
                """
            ),
            {"portfolio_id": portfolio_id},
        ).fetchall()
        assert [
            (
                row.transaction_id,
                as_decimal(row.amount),
                row.classification,
                row.timing,
            )
            for row in cashflows
        ] == [
            (
                setup_mwr_data["transaction_ids"]["deposit_1"],
                Decimal("1000"),
                "CASHFLOW_IN",
                "BOD",
            ),
            (
                setup_mwr_data["transaction_ids"]["deposit_2"],
                Decimal("200"),
                "CASHFLOW_IN",
                "BOD",
            ),
            (setup_mwr_data["transaction_ids"]["fee"], Decimal("-25"), "EXPENSE", "EOD"),
            (setup_mwr_data["transaction_ids"]["tax"], Decimal("-10"), "EXPENSE", "EOD"),
            (
                setup_mwr_data["transaction_ids"]["withdrawal"],
                Decimal("-100"),
                "CASHFLOW_OUT",
                "EOD",
            ),
        ]

        timeseries_rows = session.execute(
            text(
                """
                select distinct on (date)
                    date, bod_market_value, eod_market_value, epoch
                from position_timeseries
                where portfolio_id = :portfolio_id
                  and security_id = :security_id
                  and date in ('2025-08-01', '2025-08-15', '2025-08-16', '2025-08-17', '2025-08-18')
                order by date, epoch desc
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "security_id": setup_mwr_data["cash_security_id"],
            },
        ).fetchall()
        assert [
            (str(row.date), as_decimal(row.eod_market_value))
            for row in timeseries_rows
        ] == [
            ("2025-08-01", Decimal("1000")),
            ("2025-08-15", Decimal("1200")),
            ("2025-08-16", Decimal("1175")),
            ("2025-08-17", Decimal("1165")),
            ("2025-08-18", Decimal("1065")),
        ]
