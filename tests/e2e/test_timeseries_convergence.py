from decimal import Decimal

from .api_client import E2EApiClient
from .data_factory import unique_suffix
from .timeseries_support import (
    assert_timeseries_payload,
    has_expected_positions,
    has_expected_timeseries_rows,
    position_timeseries_request,
    seed_two_day_timeseries_scenario,
    sum_external_flows_payload,
)


def test_cash_only_staged_external_flows_are_not_doubled(
    clean_db, e2e_api_client: E2EApiClient
):
    suffix = unique_suffix()
    portfolio_id = f"E2E_CASH_STAGE_{suffix}"
    cash_security_id = f"CASH_USD_{suffix}"

    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2026-03-01",
                    "risk_exposure": "Low",
                    "investment_time_horizon": "Short",
                    "portfolio_type": "Advisory",
                    "booking_center_code": "SG",
                    "client_id": "TS_CIF",
                    "status": "Active",
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
                    "isin": f"USD_CASH_{suffix}",
                    "currency": "USD",
                    "product_type": "Cash",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates",
        {
            "business_dates": [
                {"business_date": "2026-03-16"},
                {"business_date": "2026-03-17"},
                {"business_date": "2026-03-18"},
                {"business_date": "2026-03-19"},
                {"business_date": "2026-03-20"},
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": f"DEP_1_{suffix}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2026-03-16T00:00:00Z",
                    "transaction_type": "DEPOSIT",
                    "quantity": 10000,
                    "price": 1,
                    "gross_transaction_amount": 10000,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": f"DEP_2_{suffix}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2026-03-18T00:00:00Z",
                    "transaction_type": "DEPOSIT",
                    "quantity": 5000,
                    "price": 1,
                    "gross_transaction_amount": 5000,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": f"WD_1_{suffix}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2026-03-19T00:00:00Z",
                    "transaction_type": "WITHDRAWAL",
                    "quantity": 2000,
                    "price": 1,
                    "gross_transaction_amount": 2000,
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
                    "price_date": "2026-03-16",
                    "price": 1,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2026-03-17",
                    "price": 1,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2026-03-18",
                    "price": 1,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2026-03-19",
                    "price": 1,
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2026-03-20",
                    "price": 1,
                    "currency": "USD",
                },
            ]
        },
    )

    request = {
        "as_of_date": "2026-03-20",
        "window": {"start_date": "2026-03-16", "end_date": "2026-03-20"},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "include_cash_flows": True,
        "page": {"page_size": 200},
    }

    portfolio_payload = e2e_api_client.poll_for_post_query_data(
        f"/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
        {
            "as_of_date": "2026-03-20",
            "window": {"start_date": "2026-03-16", "end_date": "2026-03-20"},
            "consumer_system": "lotus-performance",
            "frequency": "daily",
            "page": {"page_size": 200},
        },
        lambda data: data.get("performance_end_date") == "2026-03-20"
        and len(data.get("observations", [])) == 5,
        timeout=240,
        fail_message="Portfolio cash-only staged-flow timeseries did not mature.",
    )
    position_payload = e2e_api_client.poll_for_post_query_data(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        request,
        lambda data: len(data.get("rows", [])) == 5,
        timeout=240,
        fail_message="Position cash-only staged-flow timeseries did not mature.",
    )

    expected_flows = {
        "2026-03-16": Decimal("10000"),
        "2026-03-18": Decimal("5000"),
        "2026-03-19": Decimal("-2000"),
    }
    portfolio_external = {
        observation["valuation_date"]: sum_external_flows_payload(observation["cash_flows"])
        for observation in portfolio_payload["observations"]
        if observation["cash_flows"]
    }
    assert portfolio_external == expected_flows

    position_external = {
        row["valuation_date"]: sum_external_flows_payload(row["cash_flows"])
        for row in position_payload["rows"]
    }
    assert position_external == {
        "2026-03-16": Decimal("10000"),
        "2026-03-17": Decimal("0"),
        "2026-03-18": Decimal("5000"),
        "2026-03-19": Decimal("-2000"),
        "2026-03-20": Decimal("0"),
    }


def test_price_before_position_history_still_converges_to_full_day_2_timeseries(
    clean_db, e2e_api_client: E2EApiClient
):
    suffix = unique_suffix()
    portfolio_id = f"E2E_TS_RACE_{suffix}"
    stock_security_id = f"SEC_EUR_STOCK_{suffix}"
    cash_security_id = f"CASH_{suffix}"

    seed_two_day_timeseries_scenario(
        e2e_api_client,
        portfolio_id=portfolio_id,
        stock_security_id=stock_security_id,
        cash_security_id=cash_security_id,
        stock_isin=f"EU{suffix}",
        cash_isin=f"USD_CASH_{suffix}",
        deposit_tx_id=f"TS_DEP_{suffix}",
        buy_tx_id=f"TS_BUY_{suffix}",
        settle_tx_id=f"TS_CASH_SETTLE_BUY_{suffix}",
        fee_tx_id=f"TS_FEE_{suffix}",
        prices_before_transactions=True,
    )

    e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions",
        lambda data: has_expected_positions(
            data,
            stock_security_id=stock_security_id,
            cash_security_id=cash_security_id,
        ),
        timeout=240,
        fail_message=(
            "Price-before-position-history scenario did not converge to the expected stock and "
            "cash positions."
        ),
    )
    race_payload = e2e_api_client.poll_for_post_query_data(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        position_timeseries_request("2025-08-29"),
        lambda data: has_expected_timeseries_rows(
            data,
            valuation_date="2025-08-29",
            stock_security_id=stock_security_id,
            cash_security_id=cash_security_id,
        ),
        timeout=240,
        fail_message=(
            "Price-before-position-history scenario did not converge to a complete day-2 "
            "position-timeseries payload."
        ),
    )

    assert_timeseries_payload(
        race_payload,
        valuation_date="2025-08-29",
        portfolio_id=portfolio_id,
        stock_security_id=stock_security_id,
        cash_security_id=cash_security_id,
    )
