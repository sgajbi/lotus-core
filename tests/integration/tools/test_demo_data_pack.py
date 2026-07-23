import http.client
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.position.history import (
    order_position_transactions,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.reducer import (
    PositionBalanceState,
    calculate_next_position_state,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
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


def test_build_demo_bundle_uses_governed_fixed_as_of_date():
    bundle = demo_data_pack.build_demo_bundle()

    assert bundle["as_of_date"] == demo_data_pack.DEMO_SEED_CONTRACT.canonical_as_of_date


def test_history_window_does_not_move_transaction_economics():
    ci_bundle = demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)
    full_bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.DEFAULT_DEMO_HISTORY_DAYS
    )

    assert ci_bundle["transactions"] == full_bundle["transactions"]
    assert all(
        transaction["transaction_date"][:10] <= ci_bundle["as_of_date"]
        for transaction in ci_bundle["transactions"]
    )
    transactions_by_id = {
        transaction["transaction_id"]: transaction for transaction in ci_bundle["transactions"]
    }
    assert transactions_by_id["DEMO_ADV_DEP_01"]["transaction_date"] == "2023-07-21T09:00:00Z"


def test_generated_market_and_fx_economics_use_exact_decimal_strings():
    bundle = demo_data_pack.build_demo_bundle()
    cash_security_ids = {
        instrument["security_id"]
        for instrument in bundle["instruments"]
        if instrument["product_type"] == "Cash"
    }

    non_cash_prices = [
        record["price"]
        for record in bundle["market_prices"]
        if record["security_id"] not in cash_security_ids
    ]
    rates = [record["rate"] for record in bundle["fx_rates"]]

    assert non_cash_prices and all(isinstance(price, str) for price in non_cash_prices)
    assert rates and all(isinstance(rate, str) for rate in rates)
    assert all(Decimal(price).as_tuple().exponent == -2 for price in non_cash_prices)
    assert all(Decimal(rate).as_tuple().exponent == -6 for rate in rates)


def test_overlapping_reference_dates_have_identical_economics_across_history_windows():
    ci_bundle = demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)
    full_bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.DEFAULT_DEMO_HISTORY_DAYS
    )
    series_specs = (
        ("market_prices", ("security_id", "price_date"), ("price", "currency")),
        ("fx_rates", ("from_currency", "to_currency", "rate_date"), ("rate",)),
        ("index_price_series", ("index_id", "series_date"), ("index_price",)),
        ("index_return_series", ("index_id", "series_date"), ("index_return",)),
        (
            "benchmark_return_series",
            ("benchmark_id", "series_date"),
            ("benchmark_return",),
        ),
        ("risk_free_series", ("risk_free_curve_id", "series_date"), ("value",)),
    )

    for collection, key_fields, value_fields in series_specs:
        full_by_key = {
            tuple(record[field] for field in key_fields): record
            for record in full_bundle[collection]
        }
        for record in ci_bundle[collection]:
            key = tuple(record[field] for field in key_fields)
            assert key in full_by_key
            assert tuple(record[field] for field in value_fields) == tuple(
                full_by_key[key][field] for field in value_fields
            )


def test_logical_segment_identities_are_stable_across_history_windows():
    ci_segments = demo_data_pack._build_demo_pack_segments(
        demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)
    )
    full_segments = demo_data_pack._build_demo_pack_segments(
        demo_data_pack.build_demo_bundle(history_days=demo_data_pack.DEFAULT_DEMO_HISTORY_DAYS)
    )

    assert {segment.name for segment in ci_segments} == {segment.name for segment in full_segments}
    assert not any("-batch-" in segment.name for segment in ci_segments)


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


def test_ingest_demo_portfolio_data_uses_logical_market_and_fx_series(monkeypatch):
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

    segments = tuple(
        segment
        for segment in demo_data_pack._build_demo_pack_segments(bundle)
        if segment.category == "portfolio"
    )
    demo_data_pack._ingest_demo_segments(
        "http://ingestion",
        segments,
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

    market_price_series = [
        payload["market_prices"]
        for url, payload, _headers in calls
        if url == "http://ingestion/ingest/market-prices"
    ]
    fx_rate_series = [
        payload["fx_rates"]
        for url, payload, _headers in calls
        if url == "http://ingestion/ingest/fx-rates"
    ]

    assert all(len({row["security_id"] for row in series}) == 1 for series in market_price_series)
    assert all(
        len({(row["from_currency"], row["to_currency"]) for row in series}) == 1
        for series in fx_rate_series
    )
    assert sorted(
        (row for series in market_price_series for row in series),
        key=lambda row: (row["security_id"], row["price_date"]),
    ) == sorted(
        bundle["market_prices"],
        key=lambda row: (row["security_id"], row["price_date"]),
    )
    assert sorted(
        (row for series in fx_rate_series for row in series),
        key=lambda row: (row["from_currency"], row["to_currency"], row["rate_date"]),
    ) == sorted(
        bundle["fx_rates"],
        key=lambda row: (row["from_currency"], row["to_currency"], row["rate_date"]),
    )


def test_demo_pack_segment_inventory_is_unique_complete_and_logically_partitioned():
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )

    segments = demo_data_pack._build_demo_pack_segments(bundle)
    names = [segment.name for segment in segments]
    market_segments = [
        segment for segment in segments if segment.endpoint.endswith("market-prices")
    ]
    fx_segments = [segment for segment in segments if segment.endpoint.endswith("fx-rates")]
    reference_segments = [segment for segment in segments if segment.category == "reference"]

    assert len(names) == len(set(names))
    assert names[0] == "portfolio-bundle"
    # Keep a full default pack inside the app-local ingestion rate window.
    assert len(segments) <= 500
    assert sum(segment.record_count for segment in segments) <= 50_000
    assert {segment.name for segment in market_segments} == {
        f"market-prices:{security_id}"
        for security_id in {row["security_id"] for row in bundle["market_prices"]}
    }
    assert {segment.name for segment in fx_segments} == {
        f"fx-rates:{from_currency}:{to_currency}"
        for from_currency, to_currency in {
            (row["from_currency"], row["to_currency"]) for row in bundle["fx_rates"]
        }
    }
    assert all(
        segment.payload["market_prices"]
        == sorted(segment.payload["market_prices"], key=lambda row: row["price_date"])
        for segment in market_segments
    )
    assert all(
        segment.payload["fx_rates"]
        == sorted(segment.payload["fx_rates"], key=lambda row: row["rate_date"])
        for segment in fx_segments
    )
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


def test_full_default_demo_pack_stays_within_app_local_ingestion_rate_window():
    segments = demo_data_pack._build_demo_pack_segments(demo_data_pack.build_demo_bundle())

    assert len(segments) <= 500
    assert sum(segment.record_count for segment in segments) <= 50_000


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


def test_index_probe_verifies_catalog_and_both_series(monkeypatch):
    segments = (
        demo_data_pack.DemoPackSegment(
            name="indices",
            endpoint="/ingest/indices",
            payload={
                "indices": [
                    {
                        "index_id": "IDX-A",
                        "index_name": "Index A",
                        "index_currency": "USD",
                        "index_type": "equity_index",
                        "index_status": "active",
                        "index_provider": "LOTUS",
                        "index_market": "global",
                        "classification_set_id": "taxonomy-v1",
                        "classification_labels": {"asset_class": "equity"},
                        "effective_from": "2026-01-01",
                        "source_vendor": "LOTUS",
                        "source_record_id": "idx-a",
                    }
                ]
            },
            category="reference",
        ),
        demo_data_pack.DemoPackSegment(
            name="index-price-series",
            endpoint="/ingest/index-price-series",
            payload={
                "index_price_series": [
                    {
                        "index_id": "IDX-A",
                        "series_date": "2026-01-02",
                        "index_price": "100.0000",
                        "series_currency": "USD",
                        "value_convention": "close_price",
                        "quality_status": "accepted",
                    }
                ]
            },
            category="reference",
        ),
        demo_data_pack.DemoPackSegment(
            name="index-return-series",
            endpoint="/ingest/index-return-series",
            payload={
                "index_return_series": [
                    {
                        "index_id": "IDX-A",
                        "series_date": "2026-01-02",
                        "index_return": "0.0100",
                        "return_period": "1d",
                        "return_convention": "total_return_index",
                        "series_currency": "USD",
                        "quality_status": "accepted",
                    }
                ]
            },
            category="reference",
        ),
    )

    def fake_request_json(method, url, payload=None, headers=None):
        assert method == "POST"
        assert headers is None
        if url.endswith("/indices/catalog"):
            return 200, {"records": segments[0].payload["indices"]}
        if url.endswith("/price-series"):
            return 200, {
                "points": [
                    {
                        "series_date": "2026-01-02",
                        "index_price": 100,
                        "series_currency": "USD",
                        "value_convention": "close_price",
                        "quality_status": "accepted",
                    }
                ]
            }
        return 200, {
            "points": [
                {
                    "series_date": "2026-01-02",
                    "index_return": "0.01",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                    "quality_status": "accepted",
                }
            ]
        }

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._probe_index_segments(
        "http://qcp",
        as_of_date="2026-01-31",
        segments=segments,
    )

    assert result.is_complete is True
    assert result.evaluated_segments == (
        "indices",
        "index-price-series",
        "index-return-series",
    )


def test_index_probe_marks_only_evolved_price_series(monkeypatch):
    bundle = demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)
    segments = tuple(
        segment
        for segment in demo_data_pack._build_demo_pack_segments(bundle)
        if segment.name in {"indices", "index-price-series", "index-return-series"}
    )

    def fake_request_json(method, url, payload=None, headers=None):
        assert method == "POST"
        if url.endswith("/indices/catalog"):
            return 200, {"records": bundle["indices"]}
        index_id = url.split("/indices/", maxsplit=1)[1].split("/", maxsplit=1)[0]
        if url.endswith("/price-series"):
            points = [
                {
                    key: value
                    for key, value in record.items()
                    if key
                    in {
                        "series_date",
                        "index_price",
                        "series_currency",
                        "value_convention",
                        "quality_status",
                    }
                }
                for record in bundle["index_price_series"]
                if record["index_id"] == index_id
            ]
            points[0]["index_price"] = "999.0"
            return 200, {"points": points}
        return 200, {
            "points": [
                {
                    key: value
                    for key, value in record.items()
                    if key
                    in {
                        "series_date",
                        "index_return",
                        "return_period",
                        "return_convention",
                        "series_currency",
                        "quality_status",
                    }
                }
                for record in bundle["index_return_series"]
                if record["index_id"] == index_id
            ]
        }

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._probe_index_segments(
        "http://qcp",
        as_of_date=bundle["as_of_date"],
        segments=segments,
    )

    assert result.missing_segments == ("index-price-series",)


def test_benchmark_and_risk_free_probe_verifies_all_source_families(monkeypatch):
    bundle = demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)
    segments = tuple(
        segment
        for segment in demo_data_pack._build_demo_pack_segments(bundle)
        if segment.category == "reference" and not segment.name.startswith("index")
    )

    def fake_request_json(method, url, payload=None, headers=None):
        assert method == "POST"
        assert headers is None
        if url.endswith("/benchmarks/catalog"):
            return 200, {"records": bundle["benchmark_definitions"]}
        if url.endswith("/composition-window"):
            benchmark_id = url.split("/benchmarks/", maxsplit=1)[1].split("/", maxsplit=1)[0]
            return 200, {
                "segments": [
                    {
                        key: value
                        for key, value in record.items()
                        if key
                        in {
                            "index_id",
                            "composition_weight",
                            "composition_effective_from",
                            "composition_effective_to",
                            "rebalance_event_id",
                        }
                    }
                    for record in bundle["benchmark_compositions"]
                    if record["benchmark_id"] == benchmark_id
                ]
            }
        if url.endswith("/return-series"):
            benchmark_id = url.split("/benchmarks/", maxsplit=1)[1].split("/", maxsplit=1)[0]
            return 200, {
                "points": [
                    {
                        key: value
                        for key, value in record.items()
                        if key
                        in {
                            "series_date",
                            "benchmark_return",
                            "return_period",
                            "return_convention",
                            "series_currency",
                            "quality_status",
                        }
                    }
                    for record in bundle["benchmark_return_series"]
                    if record["benchmark_id"] == benchmark_id
                ]
            }
        if url.endswith("/benchmark-assignment"):
            portfolio_id = url.split("/portfolios/", maxsplit=1)[1].split("/", maxsplit=1)[0]
            return 200, next(
                record
                for record in bundle["benchmark_assignments"]
                if record["portfolio_id"] == portfolio_id
            )
        return 200, {
            "points": [
                {
                    key: value
                    for key, value in record.items()
                    if key
                    in {
                        "series_date",
                        "value",
                        "value_convention",
                        "day_count_convention",
                        "compounding_convention",
                        "series_currency",
                        "quality_status",
                    }
                }
                for record in bundle["risk_free_series"]
            ]
        }

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._probe_benchmark_and_risk_free_segments(
        "http://qcp",
        as_of_date=bundle["as_of_date"],
        segments=segments,
    )

    assert result.is_complete is True
    assert result.evaluated_segments == (
        "benchmark-definitions",
        "benchmark-compositions",
        "benchmark-return-series",
        "benchmark-assignments",
        "risk-free-series",
    )


def test_benchmark_probe_isolates_evolved_assignment(monkeypatch):
    bundle = demo_data_pack.build_demo_bundle(history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS)
    assignment_segment = next(
        segment
        for segment in demo_data_pack._build_demo_pack_segments(bundle)
        if segment.name == "benchmark-assignments"
    )
    evolved = {
        **bundle["benchmark_assignments"][0],
        "benchmark_id": demo_data_pack.SECONDARY_DEMO_BENCHMARK_ID,
    }
    monkeypatch.setattr(
        demo_data_pack,
        "_request_json",
        lambda *_args, **_kwargs: (200, evolved),
    )

    result = demo_data_pack._probe_benchmark_and_risk_free_segments(
        "http://qcp",
        as_of_date=bundle["as_of_date"],
        segments=(assignment_segment,),
    )

    assert result.missing_segments == ("benchmark-assignments",)


def test_portfolio_probe_verifies_master_reference_ledger_and_positions(monkeypatch):
    portfolio_ids = ("DEMO_DPM_EUR_001",)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=portfolio_ids,
    )
    segment = demo_data_pack._build_demo_pack_segments(bundle)[0]
    expectations = demo_data_pack._expectations_for_portfolio_ids(portfolio_ids)

    def fake_request_json(method, url, payload=None, headers=None):
        assert headers is None
        if "/analytics/portfolio-timeseries" in url:
            assert method == "POST"
            assert payload is not None
            assert payload["page"] == {"page_size": len(bundle["business_dates"])}
            return 200, {
                "resolved_window": payload["window"],
                "observations": [
                    {"valuation_date": record["business_date"]}
                    for record in bundle["business_dates"]
                ],
                "page": {
                    "returned_row_count": len(bundle["business_dates"]),
                    "next_page_token": None,
                },
                "diagnostics": {
                    "expected_business_dates_count": len(bundle["business_dates"]),
                    "missing_dates_count": 0,
                },
            }
        assert method == "GET"
        assert payload is None
        if "/instruments/" in url:
            security_id = url.split("security_id=", maxsplit=1)[1].split("&", maxsplit=1)[0]
            return 200, {
                "instruments": [
                    record
                    for record in bundle["instruments"]
                    if record["security_id"] == security_id
                ]
            }
        if "/transactions?" in url:
            return 200, {"transactions": bundle["transactions"]}
        if "/positions?" in url:
            return 200, {
                "positions": [
                    {"security_id": security_id, "quantity": str(quantity)}
                    for security_id, quantity in expectations[0].expected_terminal_quantities
                ]
            }
        return 200, bundle["portfolios"][0]

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._probe_portfolio_bundle_segment(
        "http://query",
        "http://qcp",
        as_of_date=bundle["as_of_date"],
        segment=segment,
        expectations=expectations,
    )

    assert result.is_complete is True
    assert result.evaluated_segments == ("portfolio-bundle",)


def test_portfolio_probe_rejects_evolved_transaction_economics(monkeypatch):
    portfolio_ids = ("DEMO_DPM_EUR_001",)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=portfolio_ids,
    )
    segment = demo_data_pack._build_demo_pack_segments(bundle)[0]
    expectations = demo_data_pack._expectations_for_portfolio_ids(portfolio_ids)

    def fake_request_json(method, url, payload=None, headers=None):
        if "/analytics/portfolio-timeseries" in url:
            return 200, {
                "resolved_window": payload["window"],
                "observations": [
                    {"valuation_date": record["business_date"]}
                    for record in bundle["business_dates"]
                ],
                "page": {
                    "returned_row_count": len(bundle["business_dates"]),
                    "next_page_token": None,
                },
                "diagnostics": {
                    "expected_business_dates_count": len(bundle["business_dates"]),
                    "missing_dates_count": 0,
                },
            }
        if "/instruments/" in url:
            security_id = url.split("security_id=", maxsplit=1)[1].split("&", maxsplit=1)[0]
            return 200, {
                "instruments": [
                    record
                    for record in bundle["instruments"]
                    if record["security_id"] == security_id
                ]
            }
        if "/transactions?" in url:
            transactions = [dict(record) for record in bundle["transactions"]]
            transactions[0]["gross_transaction_amount"] += 1
            return 200, {"transactions": transactions}
        if "/positions?" in url:
            return 200, {
                "positions": [
                    {"security_id": security_id, "quantity": quantity}
                    for security_id, quantity in expectations[0].expected_terminal_quantities
                ]
            }
        return 200, bundle["portfolios"][0]

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._probe_portfolio_bundle_segment(
        "http://query",
        "http://qcp",
        as_of_date=bundle["as_of_date"],
        segment=segment,
        expectations=expectations,
    )

    assert result.missing_segments == ("portfolio-bundle",)


def test_portfolio_probe_rejects_same_count_substituted_business_calendar_date(monkeypatch):
    portfolio_ids = ("DEMO_DPM_EUR_001",)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=portfolio_ids,
    )
    segment = demo_data_pack._build_demo_pack_segments(bundle)[0]
    expectations = demo_data_pack._expectations_for_portfolio_ids(portfolio_ids)

    def fake_request_json(method, url, payload=None, headers=None):
        if "/analytics/portfolio-timeseries" in url:
            observed_dates = [record["business_date"] for record in bundle["business_dates"]]
            observed_dates[-1] = "1900-01-01"
            return 200, {
                "resolved_window": payload["window"],
                "observations": [
                    {"valuation_date": valuation_date} for valuation_date in observed_dates
                ],
                "page": {
                    "returned_row_count": len(bundle["business_dates"]),
                    "next_page_token": None,
                },
                "diagnostics": {
                    "expected_business_dates_count": len(bundle["business_dates"]),
                    "missing_dates_count": 0,
                },
            }
        if "/instruments/" in url:
            security_id = url.split("security_id=", maxsplit=1)[1].split("&", maxsplit=1)[0]
            return 200, {
                "instruments": [
                    record
                    for record in bundle["instruments"]
                    if record["security_id"] == security_id
                ]
            }
        if "/transactions?" in url:
            return 200, {"transactions": bundle["transactions"]}
        if "/positions?" in url:
            return 200, {
                "positions": [
                    {"security_id": security_id, "quantity": quantity}
                    for security_id, quantity in expectations[0].expected_terminal_quantities
                ]
            }
        return 200, bundle["portfolios"][0]

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._probe_portfolio_bundle_segment(
        "http://query",
        "http://qcp",
        as_of_date=bundle["as_of_date"],
        segment=segment,
        expectations=expectations,
    )

    assert result.missing_segments == ("portfolio-bundle",)


def test_complete_pack_probe_merges_every_source_family(monkeypatch):
    portfolio_ids = ("DEMO_DPM_EUR_001",)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=portfolio_ids,
    )
    segments = demo_data_pack._build_demo_pack_segments(bundle)
    names = {segment.name for segment in segments}
    market_fx = tuple(
        segment.name
        for segment in segments
        if segment.endpoint in {"/ingest/market-prices", "/ingest/fx-rates"}
    )
    index = tuple(name for name in names if name.startswith("index") or name == "indices")
    benchmark = tuple(
        name for name in names if name.startswith("benchmark") or name == "risk-free-series"
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_portfolio_bundle_segment",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness(("portfolio-bundle",), ()),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_market_and_fx_segments",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness(
            market_fx,
            (market_fx[0],),
        ),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_index_segments",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness(index, ()),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_benchmark_and_risk_free_segments",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness(
            benchmark,
            ("risk-free-series",),
        ),
    )

    result = demo_data_pack._probe_demo_pack_completeness(
        query_base_url="http://query",
        query_control_plane_base_url="http://qcp",
        bundle=bundle,
        expectations=demo_data_pack._expectations_for_portfolio_ids(portfolio_ids),
    )

    assert set(result.evaluated_segments) == names
    assert result.missing_segments == tuple(sorted((market_fx[0], "risk-free-series")))


def test_complete_pack_probe_fails_closed_when_a_segment_has_no_evaluator(monkeypatch):
    portfolio_ids = ("DEMO_DPM_EUR_001",)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=portfolio_ids,
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_portfolio_bundle_segment",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness((), ()),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_market_and_fx_segments",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness((), ()),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_index_segments",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness((), ()),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_benchmark_and_risk_free_segments",
        lambda *_args, **_kwargs: demo_data_pack.DemoPackCompleteness((), ()),
    )

    with pytest.raises(RuntimeError, match="did not evaluate every segment"):
        demo_data_pack._probe_demo_pack_completeness(
            query_base_url="http://query",
            query_control_plane_base_url="http://qcp",
            bundle=bundle,
            expectations=demo_data_pack._expectations_for_portfolio_ids(portfolio_ids),
        )


def test_build_demo_bundle_uses_deterministic_transaction_creation_times():
    bundle = demo_data_pack.build_demo_bundle()

    assert all(
        transaction["created_at"] == transaction["transaction_date"]
        for transaction in bundle["transactions"]
    )


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
        assert all(quantity != 0 for _, quantity in item.expected_terminal_quantities)


def test_terminal_holding_expectations_match_canonical_position_reducer():
    transactions_by_position: dict[tuple[str, str], list[BookedTransaction]] = defaultdict(list)
    for record in demo_data_pack.build_demo_bundle()["transactions"]:
        transaction = BookedTransaction(
            transaction_id=record["transaction_id"],
            portfolio_id=record["portfolio_id"],
            instrument_id=record["instrument_id"],
            security_id=record["security_id"],
            transaction_date=datetime.fromisoformat(
                record["transaction_date"].replace("Z", "+00:00")
            ),
            created_at=datetime.fromisoformat(record["created_at"].replace("Z", "+00:00")),
            transaction_type=record["transaction_type"],
            quantity=Decimal(str(record["quantity"])),
            price=Decimal(str(record["price"])),
            gross_transaction_amount=Decimal(str(record["gross_transaction_amount"])),
            trade_currency=record["trade_currency"],
            currency=record["currency"],
        )
        transactions_by_position[(transaction.portfolio_id, transaction.security_id)].append(
            transaction
        )

    derived_quantities: dict[tuple[str, str], Decimal] = {}
    for position_key, transactions in transactions_by_position.items():
        state = PositionBalanceState()
        for transaction in order_position_transactions(transactions):
            state = calculate_next_position_state(state, transaction)
        derived_quantities[position_key] = state.quantity

    declared_quantities = {
        (expectation.portfolio_id, security_id): Decimal(str(quantity))
        for expectation in demo_data_pack.DEMO_EXPECTATIONS
        for security_id, quantity in expectation.expected_terminal_quantities
    }
    assert declared_quantities == derived_quantities


def test_demo_pack_idempotency_key_is_canonical_and_content_addressed():
    first = demo_data_pack._demo_pack_idempotency_key(
        segment="market-prices:SEC-A",
        payload={"market_prices": [{"price": "10", "security_id": "SEC-A"}]},
    )
    reordered = demo_data_pack._demo_pack_idempotency_key(
        segment="market-prices:SEC-A",
        payload={"market_prices": [{"security_id": "SEC-A", "price": "10"}]},
    )
    evolved = demo_data_pack._demo_pack_idempotency_key(
        segment="market-prices:SEC-A",
        payload={"market_prices": [{"security_id": "SEC-A", "price": "11"}]},
    )

    assert first == reordered
    assert first != evolved
    assert first.startswith("lotus-demo-pack:v2:market-prices:SEC-A:")


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


def test_source_complete_pack_is_zero_write_noop(monkeypatch, caplog):
    caplog.set_level("INFO", logger=demo_data_pack.LOGGER.name)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    expectations = demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",))
    segment_names = tuple(
        segment.name for segment in demo_data_pack._build_demo_pack_segments(bundle)
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_demo_pack_completeness",
        lambda **_kwargs: demo_data_pack.DemoPackCompleteness(segment_names, ()),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_segments",
        lambda *_args, **_kwargs: pytest.fail("source-complete startup must perform zero writes"),
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        query_control_plane_base_url="http://qcp",
        bundle=bundle,
        expectations=expectations,
        force_ingest=False,
    )

    assert ingested is False
    assert "reason=unchanged_pack_present" in caplog.text


def test_selected_incomplete_segment_replay_is_not_reported_as_publish(monkeypatch, caplog):
    caplog.set_level("INFO", logger=demo_data_pack.LOGGER.name)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    replayed = demo_data_pack.DemoPackIngestionOutcome(
        segment="risk-free-series",
        replayed=True,
        idempotency_key="key-1",
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_demo_pack_completeness",
        lambda **_kwargs: demo_data_pack.DemoPackCompleteness(
            ("risk-free-series",),
            ("risk-free-series",),
        ),
    )
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_segments",
        lambda *_args, **_kwargs: [replayed],
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        query_control_plane_base_url="http://qcp",
        bundle=bundle,
        expectations=demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",)),
        force_ingest=False,
    )

    assert ingested is False
    assert "reason=selected_segments_already_published" in caplog.text


@pytest.mark.parametrize("force_ingest", [False, True])
def test_first_boot_and_explicit_refresh_publish_complete_demo_pack(monkeypatch, force_ingest):
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    expected_segments = demo_data_pack._build_demo_pack_segments(bundle)
    calls: list[tuple[str, ...]] = []
    if force_ingest:
        monkeypatch.setattr(
            demo_data_pack,
            "_probe_demo_pack_completeness",
            lambda **_kwargs: pytest.fail("force refresh must bypass completeness reads"),
        )
    else:
        monkeypatch.setattr(
            demo_data_pack,
            "_probe_demo_pack_completeness",
            lambda **_kwargs: demo_data_pack.DemoPackCompleteness(
                tuple(segment.name for segment in expected_segments),
                tuple(segment.name for segment in expected_segments),
            ),
        )

    def ingest_segments(_base_url, segments, *, force_ingest):
        assert force_ingest is force_ingest_expected
        calls.append(tuple(segment.name for segment in segments))
        return [
            demo_data_pack.DemoPackIngestionOutcome(
                segment=segment.name,
                replayed=False,
                idempotency_key=None if force_ingest else f"key-{segment.name}",
            )
            for segment in segments
        ]

    force_ingest_expected = force_ingest
    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_segments",
        ingest_segments,
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        query_control_plane_base_url="http://qcp",
        bundle=bundle,
        expectations=demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",)),
        force_ingest=force_ingest,
    )

    assert ingested is True
    assert calls == [tuple(segment.name for segment in expected_segments)]


def test_partial_or_evolved_pack_publishes_only_non_replayed_segments(monkeypatch, caplog):
    caplog.set_level("INFO", logger=demo_data_pack.LOGGER.name)
    bundle = demo_data_pack.build_demo_bundle(
        history_days=demo_data_pack.MIN_DEMO_HISTORY_DAYS,
        portfolio_ids=("DEMO_DPM_EUR_001",),
    )
    published = demo_data_pack.DemoPackIngestionOutcome(
        segment="risk-free-series",
        replayed=False,
        idempotency_key="key-2",
    )
    selected: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        demo_data_pack,
        "_probe_demo_pack_completeness",
        lambda **_kwargs: demo_data_pack.DemoPackCompleteness(
            ("portfolio-bundle", "risk-free-series"),
            ("risk-free-series",),
        ),
    )

    def ingest_segments(_base_url, segments, **_kwargs):
        selected.append(tuple(segment.name for segment in segments))
        return [published]

    monkeypatch.setattr(
        demo_data_pack,
        "_ingest_demo_segments",
        ingest_segments,
    )

    ingested = demo_data_pack._ingest_demo_pack_if_needed(
        ingestion_base_url="http://ingestion",
        query_base_url="http://query",
        query_control_plane_base_url="http://qcp",
        bundle=bundle,
        expectations=demo_data_pack._expectations_for_portfolio_ids(("DEMO_DPM_EUR_001",)),
        force_ingest=False,
    )

    assert ingested is True
    assert selected == [("risk-free-series",)]
    assert "reason=missing_or_evolved_segments_selected" in caplog.text
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
        if url.endswith("/positions?as_of_date=2026-06-12"):
            return 200, {
                "positions": [
                    {
                        "security_id": "SEC_TEST",
                        "quantity": "9",
                        "valuation": {"market_value": "100.00"},
                    }
                ]
            }
        if url.endswith("/transactions?limit=200"):
            return 200, {"total": 1}
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


def test_verify_portfolio_uses_one_as_of_holdings_read_for_all_quantities(monkeypatch):
    expected = demo_data_pack.PortfolioExpectation(
        "DEMO_TEST_001",
        2,
        2,
        3,
        (("SEC_A", 10.0), ("SEC_B", -2.0)),
    )
    requested_urls: list[str] = []

    def fake_request_json(method: str, url: str, **_kwargs):
        assert method == "GET"
        requested_urls.append(url)
        if url.endswith("/positions?as_of_date=2026-06-12"):
            return 200, {
                "positions": [
                    {
                        "security_id": "SEC_A",
                        "quantity": "10",
                        "valuation": {"market_value": "100.00"},
                    },
                    {
                        "security_id": "SEC_B",
                        "quantity": "-2",
                        "valuation": {"market_value": "-20.00"},
                    },
                ]
            }
        if url.endswith("/transactions?limit=200"):
            return 200, {"total": 3}
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(demo_data_pack, "_request_json", fake_request_json)

    result = demo_data_pack._verify_portfolio(
        "http://query",
        expected,
        "2026-06-12",
        wait_seconds=1,
        poll_interval_seconds=0,
    )

    assert result == {
        "portfolio_id": "DEMO_TEST_001",
        "positions": 2,
        "valued_positions": 2,
        "transactions": 3,
        "validated_holdings": 2,
    }
    assert requested_urls == [
        "http://query/portfolios/DEMO_TEST_001/positions?as_of_date=2026-06-12",
        "http://query/portfolios/DEMO_TEST_001/transactions?limit=200",
    ]


def test_request_json_treats_remote_disconnect_as_retryable_connection_error(monkeypatch):
    def disconnecting_urlopen(*_args, **_kwargs):
        raise http.client.RemoteDisconnected("closed without response")

    monkeypatch.setattr(demo_data_pack.request, "urlopen", disconnecting_urlopen)

    with pytest.raises(RuntimeError, match="GET http://query.dev/health connection error"):
        demo_data_pack._request_json("GET", "http://query.dev/health")


def test_source_probe_treats_only_not_found_as_missing(monkeypatch):
    monkeypatch.setattr(
        demo_data_pack,
        "_request_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            demo_data_pack.DemoPackHttpError(
                method="GET",
                url="http://query/portfolios/P1",
                status_code=404,
                detail="not found",
            )
        ),
    )

    assert demo_data_pack._request_source_json("GET", "http://query/portfolios/P1") == (404, {})

    monkeypatch.setattr(
        demo_data_pack,
        "_request_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            demo_data_pack.DemoPackHttpError(
                method="GET",
                url="http://query/portfolios/P1",
                status_code=500,
                detail="failed",
            )
        ),
    )
    with pytest.raises(demo_data_pack.DemoPackHttpError, match=r"failed \(500\)"):
        demo_data_pack._request_source_json("GET", "http://query/portfolios/P1")
