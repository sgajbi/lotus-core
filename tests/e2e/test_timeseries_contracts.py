from .api_client import E2EApiClient
from .assertions import as_decimal
from .timeseries_support import (
    EXPECTED_PORTFOLIO_TIMESERIES,
    assert_timeseries_payload,
    portfolio_timeseries_request,
    position_timeseries_request,
    row_by_security_id,
)


def test_analytics_input_timeseries_contract_day_1_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        position_timeseries_request("2025-08-28"),
    )
    payload = response.json()
    assert_timeseries_payload(
        payload,
        valuation_date="2025-08-28",
        portfolio_id=portfolio_id,
        stock_security_id=setup_timeseries_data["stock_security_id"],
        cash_security_id=setup_timeseries_data["cash_security_id"],
    )


def test_analytics_input_position_timeseries_contract_day_2_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    day_1_response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        position_timeseries_request("2025-08-28"),
    )
    day_1_payload = day_1_response.json()
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        position_timeseries_request("2025-08-29"),
    )
    payload = response.json()
    assert_timeseries_payload(
        day_1_payload,
        valuation_date="2025-08-28",
        portfolio_id=portfolio_id,
        stock_security_id=setup_timeseries_data["stock_security_id"],
        cash_security_id=setup_timeseries_data["cash_security_id"],
    )
    assert_timeseries_payload(
        payload,
        valuation_date="2025-08-29",
        portfolio_id=portfolio_id,
        stock_security_id=setup_timeseries_data["stock_security_id"],
        cash_security_id=setup_timeseries_data["cash_security_id"],
    )


def test_portfolio_timeseries_contract_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    for day in ("2025-08-28", "2025-08-29"):
        response = e2e_api_client.post_query(
            f"/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
            portfolio_timeseries_request(day),
        )
        payload = response.json()
        expected = EXPECTED_PORTFOLIO_TIMESERIES[day]

        assert payload["portfolio_id"] == portfolio_id
        assert payload["portfolio_currency"] == "USD"
        assert payload["reporting_currency"] == "USD"
        assert payload["resolved_window"] == {"start_date": day, "end_date": day}
        assert payload["page"]["sort_key"] == "valuation_date:asc"
        assert payload["page"]["returned_row_count"] == 1
        assert payload["diagnostics"]["cash_flows_included"] is True
        assert payload["diagnostics"]["expected_business_dates_count"] == 1
        assert payload["diagnostics"]["returned_observation_dates_count"] == 1

        assert len(payload["observations"]) == 1
        observation = payload["observations"][0]
        assert observation["valuation_date"] == day
        assert (
            as_decimal(observation["beginning_market_value"])
            == expected["beginning_market_value"]
        )
        assert as_decimal(observation["ending_market_value"]) == expected["ending_market_value"]
        assert observation["valuation_status"] == expected["valuation_status"]
        assert observation["cash_flow_currency"] == "USD"
        assert isinstance(observation["cash_flows"], list)
        for actual_flow in observation["cash_flows"]:
            assert actual_flow["timing"] in {"bod", "eod"}
            assert actual_flow["cash_flow_type"] in {
                "external_flow",
                "internal_trade_flow",
                "expense",
                "transfer",
                "income",
                "other",
            }
            assert actual_flow["flow_scope"] in {"external", "internal", "operational"}
            assert isinstance(actual_flow["source_classification"], str)


def test_position_timeseries_contract_exposes_explicit_flow_provenance_for_trade_day(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        position_timeseries_request("2025-08-28"),
    )
    payload = response.json()
    stock_row = row_by_security_id(payload, setup_timeseries_data["stock_security_id"])
    cash_row = row_by_security_id(payload, setup_timeseries_data["cash_security_id"])

    assert [(flow["cash_flow_type"], flow["flow_scope"]) for flow in stock_row["cash_flows"]] == [
        ("internal_trade_flow", "internal")
    ]
    assert [(flow["cash_flow_type"], flow["flow_scope"]) for flow in cash_row["cash_flows"]] == [
        ("external_flow", "external"),
        ("internal_trade_flow", "internal"),
    ]
