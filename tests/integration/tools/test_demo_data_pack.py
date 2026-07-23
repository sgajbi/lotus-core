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


def test_build_demo_bundle_supports_bounded_ci_history_window():
    full_bundle = demo_data_pack.build_demo_bundle()
    ci_bundle = demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)

    assert len(ci_bundle["portfolios"]) == len(full_bundle["portfolios"])
    assert len(ci_bundle["transactions"]) == len(full_bundle["transactions"])
    assert len(ci_bundle["market_prices"]) < len(full_bundle["market_prices"])
    assert len(ci_bundle["fx_rates"]) < len(full_bundle["fx_rates"])
    assert len(ci_bundle["business_dates"]) >= 170
    assert ci_bundle["as_of_date"] == full_bundle["as_of_date"]


def test_build_demo_bundle_supports_latency_focused_portfolio_scope():
    full_bundle = demo_data_pack.build_demo_bundle(history_days=365)
    latency_bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )

    assert {item["portfolio_id"] for item in latency_bundle["portfolios"]} == {"DEMO_DPM_EUR_001"}
    assert {item["portfolio_id"] for item in latency_bundle["transactions"]} == {"DEMO_DPM_EUR_001"}
    assert len(latency_bundle["transactions"]) < len(full_bundle["transactions"])
    assert len(latency_bundle["market_prices"]) < len(full_bundle["market_prices"])
    assert len(latency_bundle["fx_rates"]) < len(full_bundle["fx_rates"])
    assert {item["security_id"] for item in latency_bundle["instruments"]} == {
        "CASH_EUR",
        "SEC_ETF_WORLD_USD",
        "SEC_SAP_DE",
    }
    assert latency_bundle["benchmark_assignments"] == []
    assert {item["from_currency"] for item in latency_bundle["fx_rates"]} == {"EUR", "USD"}
    assert {item["to_currency"] for item in latency_bundle["fx_rates"]} == {"EUR", "USD"}


def test_build_demo_bundle_rejects_unknown_portfolio_scope():
    with pytest.raises(ValueError, match="Unknown demo portfolio ids: DEMO_UNKNOWN"):
        demo_data_pack.build_demo_bundle(portfolio_ids=("DEMO_UNKNOWN",))


def test_build_demo_bundle_reference_data_covers_transaction_dates_and_as_of_date():
    bundle = demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)
    transaction_dates = {
        item["transaction_date"].split("T", maxsplit=1)[0] for item in bundle["transactions"]
    }
    required_dates = transaction_dates | {bundle["as_of_date"]}

    market_price_dates = {item["price_date"] for item in bundle["market_prices"]}
    fx_rate_dates = {item["rate_date"] for item in bundle["fx_rates"]}

    assert required_dates.issubset(market_price_dates)
    assert required_dates.issubset(fx_rate_dates)


def test_build_demo_bundle_rejects_too_short_history_window():
    with pytest.raises(
        ValueError,
        match=f"history_days must be at least {demo_data_pack.MIN_DEMO_HISTORY_DAYS}",
    ):
        demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS - 1)


def test_ingest_demo_portfolio_data_batches_market_and_fx_rows(monkeypatch):
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    calls: list[tuple[str, dict[str, object], dict[str, str] | None]] = []

    def fake_request_json(
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ):
        assert method == "POST"
        assert payload is not None
        calls.append((url, payload, headers))
        return 202, {
            "message": "Accepted for asynchronous ingestion processing.",
            "idempotency_key": headers["X-Idempotency-Key"] if headers else None,
        }

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    demo_data_pack._ingest_demo_portfolio_data(
        "http://ingestion",
        bundle,
        batch_size=200,
        force_ingest=False,
    )

    assert calls[0][0] == "http://ingestion/ingest/portfolio-bundle"
    assert "market_prices" not in calls[0][1]
    assert "fx_rates" not in calls[0][1]
    assert calls[0][1]["portfolios"] == bundle["portfolios"]
    assert calls[0][1]["transactions"] == bundle["transactions"]
    idempotency_keys = [headers["X-Idempotency-Key"] for _, _, headers in calls if headers]
    assert len(idempotency_keys) == len(calls)
    assert len(set(idempotency_keys)) == len(idempotency_keys)

    market_price_batches = [
        payload["market_prices"]
        for url, payload, _headers in calls
        if url == "http://ingestion/ingest/market-prices"
    ]
    fx_rate_batches = [
        payload["fx_rates"]
        for url, payload, _headers in calls
        if url == "http://ingestion/ingest/fx-rates"
    ]

    assert all(len(batch) <= 200 for batch in market_price_batches)
    assert all(len(batch) <= 200 for batch in fx_rate_batches)
    assert [row for batch in market_price_batches for row in batch] == bundle["market_prices"]
    assert [row for batch in fx_rate_batches for row in batch] == bundle["fx_rates"]


def test_demo_pack_segment_inventory_is_unique_complete_and_bounded():
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )

    segments = demo_data_pack._build_demo_pack_segments(bundle, batch_size=200)
    names = [segment.name for segment in segments]
    market_segments = [
        segment for segment in segments if segment.endpoint.endswith("market-prices")
    ]
    fx_segments = [segment for segment in segments if segment.endpoint.endswith("fx-rates")]
    reference_segments = [segment for segment in segments if segment.category == "reference"]

    assert len(names) == len(set(names))
    assert names[0] == "portfolio-bundle"
    assert all(segment.record_count <= 200 for segment in [*market_segments, *fx_segments])
    assert sum(segment.record_count for segment in market_segments) == len(bundle["market_prices"])
    assert sum(segment.record_count for segment in fx_segments) == len(bundle["fx_rates"])
    assert {segment.name for segment in reference_segments} == {
        "indices",
        "index-price-series",
        "index-return-series",
        "benchmark-definitions",
        "benchmark-compositions",
        "benchmark-return-series",
        "risk-free-series",
    }
    assert "benchmark-assignments" not in names


def test_market_and_fx_probe_accepts_equivalent_source_records(monkeypatch):
    segments = (
        demo_data_pack.DemoPackSegment(
            name="market_prices-batch-1",
            endpoint="/ingest/market-prices",
            payload={
                "market_prices": [
                    {
                        "security_id": "SEC-A",
                        "price_date": "2026-01-02",
                        "price": 10,
                        "currency": "USD",
                    }
                ]
            },
            category="portfolio",
        ),
        demo_data_pack.DemoPackSegment(
            name="fx_rates-batch-1",
            endpoint="/ingest/fx-rates",
            payload={
                "fx_rates": [
                    {
                        "from_currency": "USD",
                        "to_currency": "EUR",
                        "rate_date": "2026-01-02",
                        "rate": "0.9200",
                    }
                ]
            },
            category="portfolio",
        ),
    )

    def fake_request_json(method, url, payload=None, headers=None):
        assert method == "GET"
        assert payload is None
        assert headers is None
        if "/prices/" in url:
            return 200, {
                "security_id": "SEC-A",
                "prices": [{"price_date": "2026-01-02", "price": "10.000", "currency": "USD"}],
            }
        return 200, {
            "from_currency": "USD",
            "to_currency": "EUR",
            "rates": [{"rate_date": "2026-01-02", "rate": 0.92}],
        }

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._probe_market_and_fx_segments("http://query", segments)

    assert result.is_complete is True
    assert result.evaluated_segments == ("market_prices-batch-1", "fx_rates-batch-1")
    assert result.missing_segments == ()


def test_market_probe_identifies_only_the_evolved_batch(monkeypatch):
    segments = tuple(
        demo_data_pack.DemoPackSegment(
            name=f"market_prices-batch-{index}",
            endpoint="/ingest/market-prices",
            payload={
                "market_prices": [
                    {
                        "security_id": "SEC-A",
                        "price_date": f"2026-01-0{index}",
                        "price": str(index * 10),
                        "currency": "USD",
                    }
                ]
            },
            category="portfolio",
        )
        for index in (1, 2)
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_request_json",
        lambda *_args, **_kwargs: (
            200,
            {
                "security_id": "SEC-A",
                "prices": [
                    {"price_date": "2026-01-01", "price": "10", "currency": "USD"},
                    {"price_date": "2026-01-02", "price": "20.01", "currency": "USD"},
                ],
            },
        ),
    )

    result = demo_data_pack._probe_market_and_fx_segments("http://query", segments)

    assert result.is_complete is False
    assert result.missing_segments == ("market_prices-batch-2",)


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


def test_demo_pack_idempotency_key_is_canonical_and_content_addressed():
    first = demo_data_pack._demo_pack_idempotency_key(
        segment="market-prices-batch-1",
        payload={"market_prices": [{"price": "10", "security_id": "SEC-A"}]},
    )
    reordered = demo_data_pack._demo_pack_idempotency_key(
        segment="market-prices-batch-1",
        payload={"market_prices": [{"security_id": "SEC-A", "price": "10"}]},
    )
    evolved = demo_data_pack._demo_pack_idempotency_key(
        segment="market-prices-batch-1",
        payload={"market_prices": [{"security_id": "SEC-A", "price": "11"}]},
    )

    assert first == reordered
    assert first != evolved
    assert first.startswith("lotus-demo-pack:v1:market-prices-batch-1:")


def test_demo_pack_payload_classifies_idempotency_replay(monkeypatch):
    def fake_request_json(method, url, payload=None, headers=None):
        assert method == "POST"
        assert url == "http://ingestion/ingest/indices"
        assert payload == {"indices": [{"index_id": "IDX-A"}]}
        assert headers is not None
        return 202, {
            "message": demo_data_pack.IDEMPOTENCY_REPLAY_MESSAGE,
            "idempotency_key": headers["X-Idempotency-Key"],
        }

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    outcome = demo_data_pack._post_demo_pack_payload(
        "http://ingestion",
        endpoint="/ingest/indices",
        segment="indices",
        payload={"indices": [{"index_id": "IDX-A"}]},
        force_ingest=False,
    )

    assert outcome.replayed is True
    assert outcome.idempotency_key is not None


def test_demo_pack_force_refresh_omits_content_idempotency_key(monkeypatch):
    def fake_request_json(method, url, payload=None, headers=None):
        assert method == "POST"
        assert headers is None
        return 202, {"message": "Accepted", "idempotency_key": None}

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    outcome = demo_data_pack._post_demo_pack_payload(
        "http://ingestion",
        endpoint="/ingest/indices",
        segment="indices",
        payload={"indices": [{"index_id": "IDX-A"}]},
        force_ingest=True,
    )

    assert outcome.replayed is False
    assert outcome.idempotency_key is None


def test_demo_pack_payload_fails_closed_on_idempotency_acknowledgement_mismatch(monkeypatch):
    monkeypatch.setattr(
        demo_data_pack,
        "_request_json",
        lambda *_args, **_kwargs: (
            202,
            {"message": "Accepted", "idempotency_key": "unexpected-key"},
        ),
    )

    with pytest.raises(RuntimeError, match="did not preserve its idempotency key"):
        demo_data_pack._post_demo_pack_payload(
            "http://ingestion",
            endpoint="/ingest/indices",
            segment="indices",
            payload={"indices": [{"index_id": "IDX-A"}]},
            force_ingest=False,
        )


def test_all_demo_portfolios_exist_checks_every_expected_portfolio(monkeypatch):
    seen: list[str] = []

    def fake_exists(_query_base_url: str, portfolio_id: str) -> bool:
        seen.append(portfolio_id)
        return True

    monkeypatch.setattr(demo_data_pack, "_portfolio_exists", fake_exists)

    assert demo_data_pack._all_demo_portfolios_exist("http://query") is True
    assert set(seen) == {item.portfolio_id for item in demo_data_pack.DEMO_EXPECTATIONS}


def test_existing_portfolio_guard_prevents_segment_replay(monkeypatch, caplog):
    caplog.set_level("INFO", logger=demo_data_pack.LOGGER.name)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    expectations = demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",))
    monkeypatch.setattr(demo_data_pack, "_all_demo_portfolios_exist", lambda *_args: True)
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_portfolio_data",
        lambda *_args, **_kwargs: pytest.fail("portfolio data must not be replayed"),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_reference_data",
        lambda *_args, **_kwargs: pytest.fail("reference data must not be replayed"),
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        bundle=bundle,
        expectations=expectations,
        force_ingest=False,
    )

    assert ingested is False
    assert "reason=portfolio_presence_compatibility_guard" in caplog.text


def test_existing_demo_pack_reports_noop_when_every_segment_is_replayed(monkeypatch, caplog):
    caplog.set_level("INFO", logger=demo_data_pack.LOGGER.name)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    replayed = demo_data_pack.DemoPackIngestionOutcome(
        segment="portfolio-bundle",
        replayed=True,
        idempotency_key="key-1",
    )
    monkeypatch.setattr(demo_data_pack, "_all_demo_portfolios_exist", lambda *_args: False)
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_portfolio_data",
        lambda *_args, **_kwargs: [replayed],
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_reference_data",
        lambda *_args, **_kwargs: [replayed],
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        bundle=bundle,
        expectations=demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",)),
        force_ingest=False,
    )

    assert ingested is False
    assert "reason=unchanged_pack_present" in caplog.text


@pytest.mark.parametrize("force_ingest", [False, True])
def test_first_boot_and_explicit_refresh_publish_complete_demo_pack(monkeypatch, force_ingest):
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    calls: list[str] = []
    published = demo_data_pack.DemoPackIngestionOutcome(
        segment="portfolio-bundle",
        replayed=False,
        idempotency_key=None if force_ingest else "key-1",
    )
    monkeypatch.setattr(demo_data_pack, "_all_demo_portfolios_exist", lambda *_args: False)

    def ingest_portfolio(*_args, **kwargs):
        assert kwargs["force_ingest"] is force_ingest
        calls.append("portfolio")
        return [published]

    def ingest_reference(*_args, **kwargs):
        assert kwargs["force_ingest"] is force_ingest
        calls.append("reference")
        return [published]

    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_portfolio_data",
        ingest_portfolio,
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_reference_data",
        ingest_reference,
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        bundle=bundle,
        expectations=demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",)),
        force_ingest=force_ingest,
    )

    assert ingested is True
    assert calls == ["portfolio", "reference"]


def test_partial_or_evolved_pack_publishes_only_non_replayed_segments(monkeypatch, caplog):
    caplog.set_level("INFO", logger=demo_data_pack.LOGGER.name)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    replayed = demo_data_pack.DemoPackIngestionOutcome(
        segment="portfolio-bundle",
        replayed=True,
        idempotency_key="key-1",
    )
    published = demo_data_pack.DemoPackIngestionOutcome(
        segment="risk-free-series",
        replayed=False,
        idempotency_key="key-2",
    )
    monkeypatch.setattr(demo_data_pack, "_all_demo_portfolios_exist", lambda *_args: False)
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_portfolio_data",
        lambda *_args, **_kwargs: [replayed],
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_reference_data",
        lambda *_args, **_kwargs: [published],
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        bundle=bundle,
        expectations=demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",)),
        force_ingest=False,
    )

    assert ingested is True
    assert "reason=missing_or_evolved_segments_published" in caplog.text
    assert "published_segments=risk-free-series" in caplog.text


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
        if url.endswith(
            "position-history?security_id=SEC_TEST&start_date=2026-06-12&end_date=2026-06-12"
        ):
            return 200, {"positions": [{"position_date": "2026-06-12", "quantity": "9"}]}
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(demo_data_pack.time, "time", fake_time)
    monkeypatch.setattr(demo_data_pack.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    with pytest.raises(TimeoutError) as exc_info:
        demo_data_pack._verify_portfolio(
            "http://query",
            expected,
            "2026-06-12",
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
