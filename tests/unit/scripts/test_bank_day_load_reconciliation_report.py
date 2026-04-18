from scripts.bank_day_load_reconciliation_report import (
    _build_summary,
    _summarize_probe_group,
)
from scripts.bank_day_load_scenario import ApiProbeResult, SamplePortfolioResult


def test_summarize_probe_group_aggregates_matching_endpoints() -> None:
    summary = _summarize_probe_group(
        label="positions",
        api_probes=[
            ApiProbeResult(
                endpoint="http://localhost:8201/portfolios/P1/positions?as_of_date=2026-04-17",
                status_code=200,
                latency_ms_samples=[20.0, 30.0],
                p95_ms=31.0,
                median_ms=25.0,
                check_passed=True,
                failure_detail=None,
            ),
            ApiProbeResult(
                endpoint="http://localhost:8201/portfolios/P2/positions?as_of_date=2026-04-17",
                status_code=200,
                latency_ms_samples=[10.0],
                p95_ms=10.0,
                median_ms=10.0,
                check_passed=True,
                failure_detail=None,
            ),
            ApiProbeResult(
                endpoint="http://localhost:8201/portfolios/P2/transactions?limit=100",
                status_code=200,
                latency_ms_samples=[99.0],
                p95_ms=99.0,
                median_ms=99.0,
                check_passed=True,
                failure_detail=None,
            ),
        ],
        endpoint_token="/positions?",
    )

    assert summary.label == "positions"
    assert summary.probe_count == 2
    assert summary.status_codes == [200]
    assert summary.median_ms == 20.0
    assert summary.p95_ms == 31.0


def test_build_summary_flags_count_value_and_reconciliation_mismatches() -> None:
    summary = _build_summary(
        sample_portfolios=[
            SamplePortfolioResult(
                portfolio_id="P1",
                positions_count=100,
                transactions_count=100,
                support_publish_allowed=True,
                support_pending_valuation_jobs=0,
                support_pending_aggregation_jobs=0,
                support_latest_booked_position_snapshot_date="2026-04-17",
                total_market_value="11617.2163000000",
                expected_market_value="11617.2163000000",
                reconciliation_passed=True,
                reconciliation_finding_count=0,
            ),
            SamplePortfolioResult(
                portfolio_id="P2",
                positions_count=99,
                transactions_count=100,
                support_publish_allowed=True,
                support_pending_valuation_jobs=0,
                support_pending_aggregation_jobs=0,
                support_latest_booked_position_snapshot_date="2026-04-17",
                total_market_value="11600.0000000000",
                expected_market_value="11617.2163000000",
                reconciliation_passed=False,
                reconciliation_finding_count=2,
            ),
        ],
        api_probes=[
            ApiProbeResult(
                endpoint="http://localhost:8201/portfolios/P1/positions?as_of_date=2026-04-17",
                status_code=200,
                latency_ms_samples=[20.0],
                p95_ms=20.0,
                median_ms=20.0,
                check_passed=True,
                failure_detail=None,
            ),
            ApiProbeResult(
                endpoint="http://localhost:8201/portfolios/P1/transactions?limit=100",
                status_code=200,
                latency_ms_samples=[30.0],
                p95_ms=30.0,
                median_ms=30.0,
                check_passed=True,
                failure_detail=None,
            ),
            ApiProbeResult(
                endpoint="http://localhost:8202/support/portfolios/P1/overview",
                status_code=200,
                latency_ms_samples=[40.0],
                p95_ms=40.0,
                median_ms=40.0,
                check_passed=True,
                failure_detail=None,
            ),
        ],
        expected_positions_count=100,
        expected_transactions_count=100,
        expected_market_value="11617.2163000000",
    )

    assert summary.all_samples_reconciled is False
    assert summary.all_position_counts_match_expected is False
    assert summary.all_transaction_counts_match_expected is True
    assert summary.all_market_values_match_expected is False
    assert summary.expected_portfolio_market_value == "11617.2163000000"
    assert summary.positions_latency.median_ms == 20.0
    assert summary.transactions_latency.median_ms == 30.0
    assert summary.support_latency.median_ms == 40.0
