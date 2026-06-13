import http.client

import pytest

from tools import demo_data_pack


def test_build_demo_bundle_contains_multi_product_coverage():
    bundle = demo_data_pack.build_demo_bundle()

    assert len(bundle["portfolios"]) == 5
    assert len(bundle["business_dates"]) >= 6
    assert len(bundle["transactions"]) >= 36
    assert len(bundle["market_prices"]) > len(bundle["instruments"])
    assert len(bundle["fx_rates"]) >= 40

    product_types = {item["product_type"] for item in bundle["instruments"]}
    assert {"Cash", "Equity", "Bond", "ETF", "Fund", "ETC"}.issubset(product_types)

    tx_types = {item["transaction_type"] for item in bundle["transactions"]}
    assert {"DEPOSIT", "BUY", "SELL", "DIVIDEND", "FEE"}.issubset(tx_types)


def test_build_demo_bundle_contains_benchmark_seed_data():
    bundle = demo_data_pack.build_demo_bundle()

    assert (
        bundle["benchmark_verification"]["benchmark_id"] == demo_data_pack.DEFAULT_DEMO_BENCHMARK_ID
    )
    assert (
        bundle["benchmark_verification"]["portfolio_id"]
        == demo_data_pack.DEFAULT_DEMO_BENCHMARK_PORTFOLIO_ID
    )
    assert bundle["benchmark_verification"]["catalog_benchmark_ids"] == [
        demo_data_pack.DEFAULT_DEMO_BENCHMARK_ID,
        demo_data_pack.SECONDARY_DEMO_BENCHMARK_ID,
    ]
    assert len(bundle["benchmark_assignments"]) == 1
    assert len(bundle["benchmark_definitions"]) == 2
    assert len(bundle["benchmark_compositions"]) == 4
    assert len(bundle["indices"]) == 2
    assert len(bundle["index_price_series"]) > len(bundle["business_dates"]) * 2
    assert len(bundle["index_return_series"]) > len(bundle["business_dates"]) * 2
    assert len(bundle["benchmark_return_series"]) > len(bundle["business_dates"]) * 2
    assert {definition["benchmark_id"] for definition in bundle["benchmark_definitions"]} == {
        demo_data_pack.DEFAULT_DEMO_BENCHMARK_ID,
        demo_data_pack.SECONDARY_DEMO_BENCHMARK_ID,
    }
    assert {
        composition["composition_weight"] for composition in bundle["benchmark_compositions"]
    } == {"0.6000000000", "0.4000000000", "0.8000000000", "0.2000000000"}
    sector_by_index = {
        index["index_id"]: index["classification_labels"].get("sector")
        for index in bundle["indices"]
    }
    assert sector_by_index == {
        "IDX_GLOBAL_EQUITY_TR": "broad_market_equity",
        "IDX_GLOBAL_BOND_TR": "broad_market_fixed_income",
    }


def test_build_demo_bundle_contains_usd_risk_free_reference_series():
    bundle = demo_data_pack.build_demo_bundle()

    risk_free_series = bundle["risk_free_series"]
    assert risk_free_series
    assert risk_free_series[0]["series_currency"] == "USD"
    assert risk_free_series[0]["risk_free_curve_id"] == "USD_SOFR_3M"
    assert risk_free_series[0]["value_convention"] == "annualized_rate"
    assert risk_free_series[-1]["series_date"] == bundle["as_of_date"]


def test_expectations_cover_five_portfolios_with_terminal_holdings():
    expected_ids = {
        "DEMO_ADV_USD_001",
        "DEMO_DPM_EUR_001",
        "DEMO_INCOME_CHF_001",
        "DEMO_BALANCED_SGD_001",
        "DEMO_REBAL_USD_001",
    }
    assert {item.portfolio_id for item in demo_data_pack.DEMO_EXPECTATIONS} == expected_ids
    for item in demo_data_pack.DEMO_EXPECTATIONS:
        assert item.min_transactions >= 7
        assert len(item.expected_terminal_quantities) >= 3
        # Demo expectations may include short/negative terminal quantities.
        assert all(quantity != 0 for _, quantity in item.expected_terminal_quantities)


def test_all_demo_portfolios_exist_checks_every_expected_portfolio(monkeypatch):
    seen: list[str] = []

    def fake_exists(_query_base_url: str, portfolio_id: str) -> bool:
        seen.append(portfolio_id)
        return True

    monkeypatch.setattr(demo_data_pack, "_portfolio_exists", fake_exists)

    assert demo_data_pack._all_demo_portfolios_exist("http://query") is True
    assert set(seen) == {item.portfolio_id for item in demo_data_pack.DEMO_EXPECTATIONS}


def test_verify_portfolio_timeout_reports_last_observed_state(monkeypatch):
    expected = demo_data_pack.PortfolioExpectation(
        "DEMO_TEST_001",
        2,
        1,
        3,
        (("SEC_TEST", 10.0),),
    )
    time_values = iter([0.0, 0.0, 2.0])

    def fake_time() -> float:
        return next(time_values)

    def fake_request_json(method: str, url: str, **_kwargs):
        assert method == "GET"
        if url.endswith("/positions"):
            return 200, {
                "positions": [{"security_id": "SEC_TEST", "valuation": {"market_value": "100.00"}}]
            }
        if url.endswith("/transactions?limit=200"):
            return 200, {"total": 1}
        if url.endswith("position-history?security_id=SEC_TEST"):
            return 200, {"positions": [{"position_date": "2026-06-12", "quantity": "9"}]}
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(demo_data_pack.time, "time", fake_time)
    monkeypatch.setattr(demo_data_pack.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    with pytest.raises(TimeoutError) as exc_info:
        demo_data_pack._verify_portfolio(
            "http://query",
            expected,
            wait_seconds=1,
            poll_interval_seconds=0,
        )

    message = str(exc_info.value)
    assert "DEMO_TEST_001" in message
    assert "positions=1" in message
    assert "min_positions=2" in message
    assert "transactions=1" in message
    assert "min_transactions=3" in message
    assert "SEC_TEST:actual=9:expected=10" in message


def test_request_json_treats_remote_disconnect_as_retryable_connection_error(monkeypatch):
    def disconnecting_urlopen(*_args, **_kwargs):
        raise http.client.RemoteDisconnected("closed without response")

    monkeypatch.setattr(demo_data_pack.request, "urlopen", disconnecting_urlopen)

    with pytest.raises(RuntimeError, match="GET http://query.dev/health connection error"):
        demo_data_pack._request_json("GET", "http://query.dev/health")
