from datetime import date

from tools.manual_performance_seed import (
    DEFAULT_DEMO_BENCHMARK_ID,
    build_manual_performance_seed_bundle,
)


def test_build_manual_performance_seed_bundle_targets_manual_portfolio_and_business_window():
    bundle = build_manual_performance_seed_bundle(
        portfolio_id="MANUAL_PB_USD_001",
        start_date=date(2026, 3, 3),
        end_date=date(2026, 3, 10),
        benchmark_id=DEFAULT_DEMO_BENCHMARK_ID,
    )

    assert bundle["start_date"] == "2026-03-03"
    assert bundle["end_date"] == "2026-03-10"
    assert [row["business_date"] for row in bundle["business_dates"]] == [
        "2026-03-03",
        "2026-03-04",
        "2026-03-05",
        "2026-03-06",
        "2026-03-09",
        "2026-03-10",
    ]
    assert bundle["benchmark_assignments"] == [
        {
            "portfolio_id": "MANUAL_PB_USD_001",
            "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
            "effective_from": "2026-03-03",
            "assignment_source": "manual_performance_seed",
            "assignment_status": "active",
            "policy_pack_id": "demo_balanced_policy_v1",
            "source_system": "LOTUS_CORE_MANUAL_PORTFOLIO_SEED",
            "assignment_recorded_at": "2026-03-03T08:00:00Z",
            "assignment_version": 1,
        }
    ]


def test_build_manual_performance_seed_bundle_generates_prices_fx_and_benchmark_series():
    bundle = build_manual_performance_seed_bundle(
        portfolio_id="MANUAL_PB_USD_001",
        start_date=date(2026, 3, 3),
        end_date=date(2026, 3, 4),
        benchmark_id=DEFAULT_DEMO_BENCHMARK_ID,
    )

    assert len(bundle["market_prices"]) == 18
    assert len(bundle["fx_rates"]) == 4
    assert len(bundle["indices"]) == 2
    assert len(bundle["index_price_series"]) >= 4
    assert len(bundle["index_return_series"]) >= 4
    assert len(bundle["benchmark_return_series"]) >= 3

    cash_prices = [
        row for row in bundle["market_prices"] if row["security_id"] == "CASH_USD_MANUAL_PB_001"
    ]
    assert {row["price"] for row in cash_prices} == {"1.0000000000"}

    eur_usd_rates = [
        row
        for row in bundle["fx_rates"]
        if row["from_currency"] == "EUR" and row["to_currency"] == "USD"
    ]
    assert [row["rate_date"] for row in eur_usd_rates] == ["2026-03-03", "2026-03-04"]
    assert eur_usd_rates[0]["rate"] != eur_usd_rates[1]["rate"]


def test_build_manual_performance_seed_bundle_generates_calendar_daily_fx():
    bundle = build_manual_performance_seed_bundle(
        portfolio_id="MANUAL_PB_USD_001",
        start_date=date(2026, 3, 6),
        end_date=date(2026, 3, 8),
        benchmark_id=DEFAULT_DEMO_BENCHMARK_ID,
    )

    eur_usd_rates = [
        row
        for row in bundle["fx_rates"]
        if row["from_currency"] == "EUR" and row["to_currency"] == "USD"
    ]
    assert [row["rate_date"] for row in eur_usd_rates] == [
        "2026-03-06",
        "2026-03-07",
        "2026-03-08",
    ]
