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

    assert bundle["benchmark_verification"]["benchmark_id"] == demo_data_pack.DEFAULT_DEMO_BENCHMARK_ID
    assert bundle["benchmark_verification"]["portfolio_id"] == demo_data_pack.DEFAULT_DEMO_BENCHMARK_PORTFOLIO_ID
    assert len(bundle["benchmark_assignments"]) == 1
    assert len(bundle["benchmark_definitions"]) == 1
    assert len(bundle["benchmark_compositions"]) == 2
    assert len(bundle["indices"]) == 2
    assert len(bundle["index_price_series"]) > len(bundle["business_dates"]) * 2
    assert len(bundle["index_return_series"]) > len(bundle["business_dates"]) * 2
    assert len(bundle["benchmark_return_series"]) > len(bundle["business_dates"])
    assert {
        composition["composition_weight"] for composition in bundle["benchmark_compositions"]
    } == {"0.6000000000", "0.4000000000"}


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
