# tests/e2e/test_reprocessing_workflow.py
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from .api_client import E2EApiClient
from .state_assertions import assert_positions_state


@pytest.fixture(scope="module")
def setup_reprocessing_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that sets up an initial state for a position,
    in preparation for a back-dated transaction.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_REPRO_{suffix}"
    security_id = f"SEC_REPRO_AAPL_{suffix}"
    instrument_id = f"AAPL_{suffix}"
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
                    "cifId": f"REPRO_CIF_{suffix}",
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
                    "isin": f"US0378331005_REPRO_{suffix}",
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
            "transaction_id": f"{portfolio_id}_BUY_DAY1",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
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
            "transaction_id": f"{portfolio_id}_BUY_DAY3",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
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

    # 3. Wait for the business state to converge, then verify the query-facing
    # baseline. The initial two-date load can legitimately settle at a non-zero
    # epoch, so readiness must be based on the current position state rather
    # than a hard-coded snapshot epoch.
    initial_state = poll_db_until(
        query="SELECT epoch, status FROM position_state WHERE portfolio_id = :pid AND security_id = :sid",  # noqa: E501
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: r is not None and r.status == "CURRENT",
        timeout=120,
        fail_message="Initial position state did not converge to CURRENT.",
    )
    assert_positions_state(
        e2e_api_client,
        portfolio_id=portfolio_id,
        as_of_date=day3,
        expected_positions={
            security_id: {
                "quantity": Decimal("150"),
                "cost_basis": Decimal("31000"),
                "market_value": Decimal("33000"),
            }
        },
    )

    return {
        "portfolio_id": portfolio_id,
        "security_id": security_id,
        "instrument_id": instrument_id,
        "initial_epoch": int(initial_state.epoch),
    }


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
    initial_epoch = setup_reprocessing_data["initial_epoch"]
    instrument_id = setup_reprocessing_data["instrument_id"]
    day2 = "2025-09-02"

    # Initial state (from fixture): BUY 100 @ $200 (Day 1), BUY 50 @ $220 (Day 3)
    # We now ingest a SELL of 40 shares on Day 2 (back-dated).
    back_dated_payload = {
        "transactions": [
            {
                "transaction_id": f"{portfolio_id}_SELL_DAY2",
                "portfolio_id": portfolio_id,
                "instrument_id": instrument_id,
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
        validation_func=lambda r: (
            r is not None and r.epoch >= initial_epoch + 1 and r.status == "CURRENT"
        ),
        timeout=120,
        fail_message="Reprocessing did not complete and advance the epoch.",
    )

    # ASSERT 2: The realized P&L on the SELL transaction must be correct based on FIFO.
    # P&L = (40 * 215) - (40 * 200) = 8600 - 8000 = 600
    poll_db_until(
        query="SELECT realized_gain_loss FROM transactions WHERE transaction_id = :transaction_id",
        params={"transaction_id": f"{portfolio_id}_SELL_DAY2"},
        validation_func=lambda r: (
            r is not None and r.realized_gain_loss == Decimal("600.0000000000")
        ),
        timeout=30,
        fail_message="Realized P&L was not calculated correctly after reprocessing.",
    )

    # ASSERT 3: The final query-facing position must converge too.
    # Final Qty = 100 + 50 - 40 = 110
    # Final Cost = (60 * 200) + (50 * 220) = 12000 + 11000 = 23000
    assert_positions_state(
        e2e_api_client,
        portfolio_id=portfolio_id,
        as_of_date="2025-09-03",
        expected_positions={
            security_id: {
                "quantity": Decimal("110"),
                "cost_basis": Decimal("23000"),
                "market_value": Decimal("24200"),
            }
        },
    )


def test_reprocess_api_rearms_current_valuation_after_transaction_correction(
    clean_db, db_engine, e2e_api_client: E2EApiClient, poll_db_until
):
    """
    Verifies that the explicit replay API fixes an already-valued position after an upstream
    transaction correction and regenerates current-epoch valuation snapshots.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_REPLAY_FIX_{suffix}"
    security_id = f"SEC_REPLAY_FIX_{suffix}"
    instrument_id = f"INST_REPLAY_FIX_{suffix}"
    day1, day2, day3 = "2025-10-01", "2025-10-02", "2025-10-03"
    day1_transaction_id = f"{portfolio_id}_BUY_DAY1"

    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": f"REPLAY_CIF_{suffix}",
                    "status": "ACTIVE",
                    "riskExposure": "balanced",
                    "investmentTimeHorizon": "7Y_PLUS",
                    "portfolioType": "DISCRETIONARY",
                    "bookingCenter": "SG",
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
                    "name": "Replay Correction Equity",
                    "isin": f"USREPLAY{suffix}",
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
                {"securityId": security_id, "priceDate": day1, "price": 100.0, "currency": "USD"},
                {"securityId": security_id, "priceDate": day2, "price": 110.0, "currency": "USD"},
                {"securityId": security_id, "priceDate": day3, "price": 120.0, "currency": "USD"},
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": day1_transaction_id,
                    "portfolio_id": portfolio_id,
                    "instrument_id": instrument_id,
                    "security_id": security_id,
                    "transaction_date": f"{day1}T10:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 100,
                    "price": 100,
                    "gross_transaction_amount": 10000,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": f"{portfolio_id}_BUY_DAY3",
                    "portfolio_id": portfolio_id,
                    "instrument_id": instrument_id,
                    "security_id": security_id,
                    "transaction_date": f"{day3}T10:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 50,
                    "price": 120,
                    "gross_transaction_amount": 6000,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
            ]
        },
    )

    initial_state = poll_db_until(
        query=(
            "SELECT epoch, watermark_date, status FROM position_state "
            "WHERE portfolio_id = :pid AND security_id = :sid"
        ),
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: (
            r is not None and r.status == "CURRENT" and str(r.watermark_date) == day3
        ),
        timeout=120,
        fail_message="Initial replay correction position state did not converge.",
    )
    assert_positions_state(
        e2e_api_client,
        portfolio_id=portfolio_id,
        as_of_date=day3,
        expected_positions={
            security_id: {
                "quantity": Decimal("150"),
                "cost_basis": Decimal("16000"),
                "market_value": Decimal("18000"),
            }
        },
    )

    with db_engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE transactions
                SET quantity = 120,
                    gross_transaction_amount = 12000,
                    updated_at = NOW()
                WHERE transaction_id = :transaction_id
                """
            ),
            {"transaction_id": day1_transaction_id},
        )

    response = e2e_api_client.reprocess_transactions([day1_transaction_id])
    assert response.status_code == 202
    assert response.json()["accepted_count"] == 1

    poll_db_until(
        query=(
            "SELECT ps.epoch, ps.watermark_date, ps.status, dps.quantity, dps.market_value "
            "FROM position_state ps "
            "JOIN daily_position_snapshots dps "
            "  ON dps.portfolio_id = ps.portfolio_id "
            " AND dps.security_id = ps.security_id "
            " AND dps.epoch = ps.epoch "
            "WHERE ps.portfolio_id = :pid "
            "  AND ps.security_id = :sid "
            "  AND dps.date = :as_of_date"
        ),
        params={"pid": portfolio_id, "sid": security_id, "as_of_date": day3},
        validation_func=lambda r: (
            r is not None
            and r.epoch >= int(initial_state.epoch) + 1
            and r.status == "CURRENT"
            and r.quantity == Decimal("170.0000000000")
            and r.market_value == Decimal("20400.0000000000")
        ),
        timeout=180,
        fail_message="Replay API did not regenerate the current-epoch valuation snapshot.",
    )

    assert_positions_state(
        e2e_api_client,
        portfolio_id=portfolio_id,
        as_of_date=day3,
        expected_positions={
            security_id: {
                "quantity": Decimal("170"),
                "cost_basis": Decimal("18000"),
                "market_value": Decimal("20400"),
            }
        },
    )
