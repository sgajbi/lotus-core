from datetime import date

from scripts import db_partition_advisor


def test_partition_candidates_cover_core_fact_tables():
    candidate_tables = {
        candidate.table_name for candidate in db_partition_advisor.PARTITION_CANDIDATES
    }

    assert {
        "transactions",
        "position_history",
        "daily_position_snapshots",
        "cashflows",
        "position_timeseries",
        "portfolio_timeseries",
        "market_prices",
        "fx_rates",
        "index_price_series",
        "index_return_series",
        "benchmark_return_series",
        "risk_free_series",
    }.issubset(candidate_tables)


def test_partition_candidates_cover_market_reference_series_tables():
    candidates = {
        candidate.table_name: candidate for candidate in db_partition_advisor.PARTITION_CANDIDATES
    }

    assert candidates["fx_rates"].partition_column == "rate_date"
    assert candidates["index_price_series"].partition_column == "series_date"
    assert candidates["index_return_series"].partition_column == "series_date"
    assert candidates["benchmark_return_series"].partition_column == "series_date"
    assert candidates["risk_free_series"].partition_column == "series_date"


def test_generate_monthly_partition_sql_uses_safe_bounds():
    candidate = next(
        candidate
        for candidate in db_partition_advisor.PARTITION_CANDIDATES
        if candidate.table_name == "transactions"
    )

    statements = db_partition_advisor.generate_monthly_partition_sql(
        candidate,
        start_month=date(2026, 5, 28),
        months=2,
    )

    assert statements == [
        (
            'CREATE TABLE IF NOT EXISTS "transactions_y2026m05" '
            'PARTITION OF "transactions" '
            "FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');"
        ),
        (
            'CREATE TABLE IF NOT EXISTS "transactions_y2026m06" '
            'PARTITION OF "transactions" '
            "FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');"
        ),
    ]


def test_build_report_keeps_execution_conservative_without_status():
    report = db_partition_advisor.build_report(
        as_of=date(2026, 5, 28),
        horizon_months=1,
    )
    transaction_candidate = next(
        candidate for candidate in report["candidates"] if candidate["table_name"] == "transactions"
    )

    assert report["generated_for_month"] == "2026-05-01"
    assert "execute only for tables already converted" in report["execution_policy"]
    assert transaction_candidate["automation_mode"] == (
        "monthly-range-create-if-parent-partitioned"
    )
    assert transaction_candidate["status"] is None
    assert transaction_candidate["recommended_partition_key"] == "transaction_date"
