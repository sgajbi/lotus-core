# tests/e2e/test_5_day_workflow.py
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from .api_client import E2EApiClient

# Constants for our test data
PORTFOLIO_ID = "E2E_WORKFLOW_01"
CASH_USD_ID = "CASH_USD"
CASH_EUR_ID = "CASH_EUR"
AAPL_ID = "SEC_AAPL_E2E"
IBM_ID = "SEC_IBM_E2E"

DAY_1 = "2025-08-19"
DAY_2 = "2025-08-20"
DAY_3 = "2025-08-21"
DAY_4 = "2025-08-22"
DAY_5 = "2025-08-23"


@pytest.fixture(scope="module")
def setup_prerequisites(clean_db_module, e2e_api_client: E2EApiClient):
    """
    A module-scoped fixture that ingests all prerequisite static data for the workflow.
    """
    # Ingest Portfolio
    portfolio_payload = {
        "portfolios": [
            {
                "portfolioId": PORTFOLIO_ID,
                "baseCurrency": "USD",
                "openDate": "2025-01-01",
                "cifId": "E2E_WF_CIF_01",
                "status": "ACTIVE",
                "riskExposure": "High",
                "investmentTimeHorizon": "Long",
                "portfolioType": "Discretionary",
                "bookingCenter": "SG",
            }
        ]
    }
    e2e_api_client.ingest("/ingest/portfolios", portfolio_payload)

    # Ingest Instruments
    instruments_payload = {
        "instruments": [
            {
                "securityId": CASH_USD_ID,
                "name": "US Dollar",
                "isin": "CASH_USD_ISIN",
                "instrumentCurrency": "USD",
                "productType": "Cash",
            },
            {
                "securityId": CASH_EUR_ID,
                "name": "Euro",
                "isin": "CASH_EUR_ISIN",
                "instrumentCurrency": "EUR",
                "productType": "Cash",
            },
            {
                "securityId": AAPL_ID,
                "name": "Apple Inc.",
                "isin": "US0378331005_E2E",
                "instrumentCurrency": "USD",
                "productType": "Equity",
            },
            {
                "securityId": IBM_ID,
                "name": "IBM Corp.",
                "isin": "US4592001014_E2E",
                "instrumentCurrency": "USD",
                "productType": "Equity",
            },
        ]
    }
    e2e_api_client.ingest("/ingest/instruments", instruments_payload)

    # Use a poll to ensure prerequisites are available before tests start
    e2e_api_client.poll_for_data(
        f"/portfolios?portfolio_id={PORTFOLIO_ID}",
        lambda data: data.get("portfolios") and len(data["portfolios"]) == 1,
    )
    e2e_api_client.poll_for_data(
        "/instruments",
        lambda data: (
            isinstance(data.get("instruments"), list)
            and {inst.get("security_id") for inst in data["instruments"]}.issuperset(
                {CASH_USD_ID, CASH_EUR_ID, AAPL_ID, IBM_ID}
            )
        ),
    )


@pytest.mark.dependency()
def test_prerequisites_are_loaded(setup_prerequisites, db_engine: Engine):
    """
    Verifies that the portfolio and instruments from the setup fixture
    have been successfully persisted to the database.
    """
    with Session(db_engine) as session:
        portfolio_count = session.execute(
            text("SELECT count(*) FROM portfolios WHERE portfolio_id = :pid"), {"pid": PORTFOLIO_ID}
        ).scalar()
        assert portfolio_count == 1, f"Portfolio {PORTFOLIO_ID} was not created."

        instrument_ids = [CASH_USD_ID, CASH_EUR_ID, AAPL_ID, IBM_ID]
        instrument_count = session.execute(
            text("SELECT count(*) FROM instruments WHERE security_id IN :ids"),
            {"ids": tuple(instrument_ids)},
        ).scalar()
        assert instrument_count == 4, "Not all instruments were created."


@pytest.mark.dependency(depends=["test_prerequisites_are_loaded"])
def test_day_1_workflow(setup_prerequisites, e2e_api_client: E2EApiClient, poll_db_until):
    """
    Tests Day 1: Ingests a business date, a deposit, and a cash price,
    then verifies the final state of the daily snapshot.
    """
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": DAY_1}]})
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": "TXN_DAY1_DEPOSIT_01",
                    "portfolio_id": PORTFOLIO_ID,
                    "instrument_id": "CASH_USD",
                    "security_id": CASH_USD_ID,
                    "transaction_date": f"{DAY_1}T10:00:00Z",
                    "transaction_type": "DEPOSIT",
                    "quantity": 1000000,
                    "price": 1.0,
                    "gross_transaction_amount": 1000000.0,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {"securityId": CASH_USD_ID, "priceDate": DAY_1, "price": 1.0, "currency": "USD"}
            ]
        },
    )

    query = "SELECT valuation_status FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"  # noqa: E501
    params = {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_1}
    poll_db_until(query, lambda r: r is not None and r.valuation_status == "VALUED_CURRENT", params)


@pytest.mark.dependency(depends=["test_day_1_workflow"])
def test_day_2_workflow(setup_prerequisites, e2e_api_client: E2EApiClient, poll_db_until):
    """
    Tests Day 2: Ingests a stock purchase and verifies the final state
    of the portfolio time series.
    """
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": DAY_2}]})
    transactions_payload = {
        "transactions": [
            {
                "transaction_id": "TXN_DAY2_BUY_AAPL_01",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": AAPL_ID,
                "instrument_id": AAPL_ID,
                "transaction_date": f"{DAY_2}T11:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1000,
                "price": 175.0,
                "gross_transaction_amount": 175000.0,
                "trade_fee": 25.50,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "TXN_DAY2_CASH_SETTLE_01",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": CASH_USD_ID,
                "instrument_id": "CASH_USD",
                "transaction_date": f"{DAY_2}T11:00:00Z",
                "transaction_type": "SELL",
                "quantity": 175025.50,
                "price": 1.0,
                "gross_transaction_amount": 175025.50,
                "trade_currency": "USD",
                "currency": "USD",
            },
        ]
    }
    e2e_api_client.ingest("/ingest/transactions", transactions_payload)
    prices_payload = {
        "market_prices": [
            {"securityId": AAPL_ID, "priceDate": DAY_2, "price": 178.0, "currency": "USD"},
            {"securityId": CASH_USD_ID, "priceDate": DAY_2, "price": 1.0, "currency": "USD"},
        ]
    }
    e2e_api_client.ingest("/ingest/market-prices", prices_payload)

    query = "SELECT eod_market_value FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date"  # noqa: E501
    params = {"pid": PORTFOLIO_ID, "date": DAY_2}
    expected_eod_mv = Decimal("1002974.5000000000")
    poll_db_until(query, lambda r: r is not None and r.eod_market_value == expected_eod_mv, params)


@pytest.mark.dependency(depends=["test_day_2_workflow"])
def test_day_3_workflow(setup_prerequisites, e2e_api_client: E2EApiClient, poll_db_until):
    """
    Tests Day 3: Ingests another stock purchase and verifies the final state
    of the portfolio time series.
    """
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": DAY_3}]})
    transactions_payload = {
        "transactions": [
            {
                "transaction_id": "TXN_DAY3_BUY_IBM_01",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": IBM_ID,
                "instrument_id": IBM_ID,
                "transaction_date": f"{DAY_3}T12:00:00Z",
                "transaction_type": "BUY",
                "quantity": 500,
                "price": 140.0,
                "gross_transaction_amount": 70000.0,
                "trade_fee": 15.00,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "TXN_DAY3_CASH_SETTLE_02",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": CASH_USD_ID,
                "instrument_id": "CASH_USD",
                "transaction_date": f"{DAY_3}T12:00:00Z",
                "transaction_type": "SELL",
                "quantity": 70015.00,
                "price": 1.0,
                "gross_transaction_amount": 70015.00,
                "trade_currency": "USD",
                "currency": "USD",
            },
        ]
    }
    e2e_api_client.ingest("/ingest/transactions", transactions_payload)
    prices_payload = {
        "market_prices": [
            {"securityId": AAPL_ID, "priceDate": DAY_3, "price": 180.0, "currency": "USD"},
            {"securityId": IBM_ID, "priceDate": DAY_3, "price": 142.0, "currency": "USD"},
            {"securityId": CASH_USD_ID, "priceDate": DAY_3, "price": 1.0, "currency": "USD"},
        ]
    }
    e2e_api_client.ingest("/ingest/market-prices", prices_payload)

    query = "SELECT eod_market_value FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date"  # noqa: E501
    params = {"pid": PORTFOLIO_ID, "date": DAY_3}
    expected_eod_mv = Decimal("1005959.5000000000")
    poll_db_until(query, lambda r: r is not None and r.eod_market_value == expected_eod_mv, params)


@pytest.mark.dependency(depends=["test_day_3_workflow"])
def test_day_4_workflow(setup_prerequisites, e2e_api_client: E2EApiClient, poll_db_until):
    """
    Tests Day 4: Ingests a stock sale and verifies the calculated
    realized gain/loss is correct.
    """
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": DAY_4}]})
    transactions_payload = {
        "transactions": [
            {
                "transaction_id": "TXN_DAY4_SELL_AAPL_01",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": AAPL_ID,
                "instrument_id": AAPL_ID,
                "transaction_date": f"{DAY_4}T13:00:00Z",
                "transaction_type": "SELL",
                "quantity": 200,
                "price": 182.0,
                "gross_transaction_amount": 36400.0,
                "trade_fee": 5.00,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "TXN_DAY4_CASH_SETTLE_03",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": CASH_USD_ID,
                "instrument_id": "CASH_USD",
                "transaction_date": f"{DAY_4}T13:00:00Z",
                "transaction_type": "BUY",
                "quantity": 36395.00,
                "price": 1.0,
                "gross_transaction_amount": 36395.00,
                "trade_currency": "USD",
                "currency": "USD",
            },
        ]
    }
    e2e_api_client.ingest("/ingest/transactions", transactions_payload)
    prices_payload = {
        "market_prices": [
            {"securityId": AAPL_ID, "priceDate": DAY_4, "price": 181.0, "currency": "USD"},
            {"securityId": IBM_ID, "priceDate": DAY_4, "price": 141.0, "currency": "USD"},
            {"securityId": CASH_USD_ID, "priceDate": DAY_4, "price": 1.0, "currency": "USD"},
        ]
    }
    e2e_api_client.ingest("/ingest/market-prices", prices_payload)

    query = "SELECT realized_gain_loss FROM transactions WHERE transaction_id = :txn_id"
    params = {"txn_id": "TXN_DAY4_SELL_AAPL_01"}
    expected_pnl = Decimal("1389.9000000000")

    def validation_func(result):
        return (
            result is not None
            and result.realized_gain_loss is not None
            and result.realized_gain_loss == expected_pnl
        )

    poll_db_until(query, validation_func, params)


@pytest.mark.dependency(depends=["test_day_4_workflow"])
def test_day_5_workflow(setup_prerequisites, e2e_api_client: E2EApiClient, poll_db_until):
    """
    Tests Day 5: Ingests a dividend and verifies the final portfolio value.
    """
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": DAY_5}]})
    transactions_payload = {
        "transactions": [
            {
                "transaction_id": "TXN_DAY5_DIV_IBM_01",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": IBM_ID,
                "instrument_id": IBM_ID,
                "transaction_date": f"{DAY_5}T09:00:00Z",
                "transaction_type": "DIVIDEND",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 750.0,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "TXN_DAY5_CASH_SETTLE_04",
                "portfolio_id": PORTFOLIO_ID,
                "security_id": CASH_USD_ID,
                "instrument_id": "CASH_USD",
                "transaction_date": f"{DAY_5}T09:00:00Z",
                "transaction_type": "BUY",
                "quantity": 750.00,
                "price": 1.0,
                "gross_transaction_amount": 750.00,
                "trade_currency": "USD",
                "currency": "USD",
            },
        ]
    }
    e2e_api_client.ingest("/ingest/transactions", transactions_payload)
    prices_payload = {
        "market_prices": [
            {"securityId": AAPL_ID, "priceDate": DAY_5, "price": 185.0, "currency": "USD"},
            {"securityId": IBM_ID, "priceDate": DAY_5, "price": 140.0, "currency": "USD"},
            {"securityId": CASH_USD_ID, "priceDate": DAY_5, "price": 1.0, "currency": "USD"},
        ]
    }
    e2e_api_client.ingest("/ingest/market-prices", prices_payload)

    query = "SELECT eod_market_value FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date"  # noqa: E501
    params = {"pid": PORTFOLIO_ID, "date": DAY_5}
    expected_eod_mv = Decimal("1010104.5000000000")
    poll_db_until(
        query,
        lambda r: r is not None and r.eod_market_value == expected_eod_mv,
        params,
        timeout=180,
    )
