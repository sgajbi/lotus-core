from decimal import Decimal

from .api_client import E2EApiClient


def test_dual_leg_upstream_settlement_cashflow_authority(
    setup_dual_leg_settlement_scenario, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_dual_leg_settlement_scenario["portfolio_id"]
    buy_txn_id = setup_dual_leg_settlement_scenario["buy_txn_id"]
    cash_txn_id = setup_dual_leg_settlement_scenario["cash_txn_id"]

    response = e2e_api_client.query(f"/portfolios/{portfolio_id}/transactions?limit=50")
    body = response.json()
    tx_by_id = {tx["transaction_id"]: tx for tx in body["transactions"]}

    assert buy_txn_id in tx_by_id
    assert cash_txn_id in tx_by_id
    assert tx_by_id[buy_txn_id]["external_cash_transaction_id"] == cash_txn_id
    assert tx_by_id[cash_txn_id]["originating_transaction_id"] == buy_txn_id
    assert tx_by_id[buy_txn_id]["cash_entry_mode"] == "UPSTREAM_PROVIDED"
    assert tx_by_id[cash_txn_id]["transaction_type"] == "ADJUSTMENT"


def test_dual_leg_upstream_settlement_position_timeseries_flows_net_to_zero(
    setup_dual_leg_settlement_scenario, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_dual_leg_settlement_scenario["portfolio_id"]
    security_id = setup_dual_leg_settlement_scenario["security_id"]
    cash_security_id = setup_dual_leg_settlement_scenario["cash_security_id"]

    e2e_api_client.ingest(
        "/ingest/business-dates",
        {"business_dates": [{"business_date": "2026-03-02"}]},
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {
                    "security_id": security_id,
                    "price_date": "2026-03-02",
                    "price": "100",
                    "currency": "USD",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2026-03-02",
                    "price": "1",
                    "currency": "USD",
                },
            ]
        },
    )

    payload = {
        "as_of_date": "2026-03-02",
        "window": {"start_date": "2026-03-02", "end_date": "2026-03-02"},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "dimensions": [],
        "include_cash_flows": True,
        "filters": {},
        "page": {"page_size": 50},
    }

    response_payload = e2e_api_client.poll_for_post_query_data(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        payload,
        lambda data: len(data.get("rows", [])) >= 2
        and {
            row.get("security_id")
            for row in data.get("rows", [])
            if row.get("valuation_date") == "2026-03-02"
        }
        >= {security_id, cash_security_id},
        timeout=240,
        fail_message=(
            "Dual-leg position-timeseries rows were not available for acquisition-day validation."
        ),
    )

    row_by_security = {row["security_id"]: row for row in response_payload["rows"]}
    stock_row = row_by_security[security_id]
    cash_row = row_by_security[cash_security_id]

    stock_flow_total = sum(Decimal(str(flow["amount"])) for flow in stock_row["cash_flows"])
    cash_flow_total = sum(Decimal(str(flow["amount"])) for flow in cash_row["cash_flows"])
    stock_beginning_value = Decimal(
        str(stock_row["beginning_market_value_position_currency"])
    )
    stock_ending_value = Decimal(str(stock_row["ending_market_value_position_currency"]))
    cash_beginning_value = Decimal(str(cash_row["beginning_market_value_position_currency"]))
    cash_ending_value = Decimal(str(cash_row["ending_market_value_position_currency"]))

    assert stock_beginning_value == Decimal("1000")
    assert stock_ending_value == Decimal("1000")
    assert cash_beginning_value == Decimal("-1000")
    assert cash_ending_value == Decimal("-1000")
    assert stock_beginning_value + cash_beginning_value == Decimal("0")
    assert stock_ending_value + cash_ending_value == Decimal("0")
    assert stock_flow_total == Decimal("1000")
    assert cash_flow_total == Decimal("-1000")
    assert stock_flow_total + cash_flow_total == Decimal("0")
    assert [(flow["cash_flow_type"], flow["flow_scope"]) for flow in stock_row["cash_flows"]] == [
        ("internal_trade_flow", "internal")
    ]
    assert [(flow["cash_flow_type"], flow["flow_scope"]) for flow in cash_row["cash_flows"]] == [
        ("internal_trade_flow", "internal")
    ]
