# tests/e2e/test_reprocessing_workflow.py
from decimal import Decimal

import pytest

from .api_client import E2EApiClient
from .assertions import as_decimal


@pytest.fixture(scope="module")
def setup_reprocessing_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that sets up an initial state for a position,
    in preparation for a back-dated transaction.
    """
    portfolio_id = "E2E_REPRO_01"
    security_id = "SEC_REPRO_AAPL"
    day1, day2, day3 = "2025-09-01", "2025-09-02", "2025-09-03"

    # 1. Ingest prerequisites
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": "REPRO_CIF",
                    "status": "ACTIVE",
                    "riskExposure": "a",
                    "investmentTimeHorizon": "b",
                    "portfolioType": "c",
                    "bookingCenter": "d",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "securityId": security_id,
                    "name": "Apple Repro",
                    "isin": "US0378331005_REPRO",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates",
        {
            "business_dates": [
                {"businessDate": day1},
                {"businessDate": day2},
                {"businessDate": day3},
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {"securityId": security_id, "priceDate": day1, "price": 200.0, "currency": "USD"},
                {"securityId": security_id, "priceDate": day2, "price": 215.0, "currency": "USD"},
                {"securityId": security_id, "priceDate": day3, "price": 220.0, "currency": "USD"},
            ]
        },
    )

    # 2. Ingest initial transactions on Day 1 and Day 3
    transactions = [
        {
            "transaction_id": "REPRO_BUY_DAY1",
            "portfolio_id": portfolio_id,
            "instrument_id": "AAPL",
            "security_id": security_id,
            "transaction_date": f"{day1}T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 200,
            "gross_transaction_amount": 20000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": "REPRO_BUY_DAY3",
            "portfolio_id": portfolio_id,
            "instrument_id": "AAPL",
            "security_id": security_id,
            "transaction_date": f"{day3}T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 50,
            "price": 220,
            "gross_transaction_amount": 11000,
            "trade_currency": "USD",
            "currency": "USD",
        },
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})

    # 3. FIX: Poll until the snapshot for the latest day is fully valued.
    # This is the definitive indicator that the initial state is ready for the test.
    poll_db_until(
        query="SELECT valuation_status FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date AND epoch = 0",  # noqa: E501
        params={"pid": portfolio_id, "sid": security_id, "date": day3},
        validation_func=lambda r: r is not None and r.valuation_status == "VALUED_CURRENT",
        timeout=120,
        fail_message="Initial snapshot for Day 3 was not created and valued in epoch 0.",
    )

    return {"portfolio_id": portfolio_id, "security_id": security_id}


def test_back_dated_transaction_triggers_reprocessing_and_corrects_state(
    setup_reprocessing_data, e2e_api_client: E2EApiClient, poll_db_until
):
    """
    Verifies that ingesting a back-dated transaction triggers an epoch increment
    and leads to a corrected final position state and P&L.
    """
    # ARRANGE
    portfolio_id = setup_reprocessing_data["portfolio_id"]
    security_id = setup_reprocessing_data["security_id"]
    day2 = "2025-09-02"

    # Initial state (from fixture): BUY 100 @ $200 (Day 1), BUY 50 @ $220 (Day 3)
    # We now ingest a SELL of 40 shares on Day 2 (back-dated).
    back_dated_payload = {
        "transactions": [
            {
                "transaction_id": "REPRO_SELL_DAY2",
                "portfolio_id": portfolio_id,
                "instrument_id": "AAPL",
                "security_id": security_id,
                "transaction_date": f"{day2}T11:00:00Z",
                "transaction_type": "SELL",
                "quantity": 40,
                "price": 215,
                "gross_transaction_amount": 8600,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    # ACT: Ingest the back-dated transaction
    e2e_api_client.ingest("/ingest/transactions", back_dated_payload)

    # ASSERT 1: The epoch must increment to 1 and the state must return to CURRENT.
    poll_db_until(
        query="SELECT epoch, status FROM position_state WHERE portfolio_id = :pid AND security_id = :sid",  # noqa: E501
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: r is not None and r.epoch == 1 and r.status == "CURRENT",
        timeout=120,
        fail_message="Reprocessing did not complete and increment epoch to 1.",
    )

    # ASSERT 2: The realized P&L on the SELL transaction must be correct based on FIFO.
    # P&L = (40 * 215) - (40 * 200) = 8600 - 8000 = 600
    poll_db_until(
        query="SELECT realized_gain_loss FROM transactions WHERE transaction_id = 'REPRO_SELL_DAY2'",  # noqa: E501
        params={},
        validation_func=lambda r: r is not None
        and r.realized_gain_loss == Decimal("600.0000000000"),
        timeout=30,
        fail_message="Realized P&L was not calculated correctly after reprocessing.",
    )

    # ASSERT 3: The final query-facing position must converge too.
    # Final Qty = 100 + 50 - 40 = 110
    # Final Cost = (60 * 200) + (50 * 220) = 12000 + 11000 = 23000
    def _has_expected_position(data: dict) -> bool:
        positions = data.get("positions", [])
        if len(positions) != 1:
            return False

        position = positions[0]
        return (
            as_decimal(position["quantity"]) == Decimal("110")
            and as_decimal(position["cost_basis"]) == Decimal("23000")
        )

    data = e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions",
        _has_expected_position,
        timeout=180,
        fail_message="Reprocessing did not converge to the expected final position.",
    )

    position = data["positions"][0]
    assert as_decimal(position["quantity"]) == Decimal("110")
    assert as_decimal(position["cost_basis"]) == Decimal("23000")
