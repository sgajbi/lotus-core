from argparse import Namespace
from decimal import Decimal

from scripts.bank_day_load_scenario import (
    ApiProbeResult,
    DatabaseTieOut,
    HealthSample,
    InstrumentSpec,
    LogEvidence,
    SamplePortfolioResult,
    ScenarioReport,
    _build_fx_rates_payload,
    _build_instrument_specs,
    _build_instruments_payload,
    _evaluate_report,
    _finalize_report,
    expected_portfolio_market_value,
    iter_transaction_batches,
)


def test_build_instrument_specs_cycles_currencies_and_prices() -> None:
    specs = _build_instrument_specs(run_id="RUN1", instrument_count=5)

    assert [spec.currency for spec in specs] == ["USD", "EUR", "SGD", "GBP", "USD"]
    assert specs[0].security_id == "LOAD_RUN1_SEC_001"
    assert specs[0].trade_price == Decimal("50.00")
    assert specs[0].market_price == Decimal("50.50")
    assert specs[4].trade_price == Decimal("55.00")
    assert specs[4].market_price == Decimal("55.55")


def test_build_instruments_payload_generates_run_unique_isins() -> None:
    run_one_payload = _build_instruments_payload(
        _build_instrument_specs(run_id="20260418T044202Z", instrument_count=2)
    )
    run_two_payload = _build_instruments_payload(
        _build_instrument_specs(run_id="20260418T045917Z", instrument_count=2)
    )

    assert run_one_payload[0]["isin"] != run_two_payload[0]["isin"]
    assert len(run_one_payload[0]["isin"]) == 12


def test_build_fx_rates_payload_returns_full_cross_currency_matrix() -> None:
    payload = _build_fx_rates_payload(
        currencies=("USD", "EUR", "SGD"),
        rate_date="2026-04-17",
    )

    assert len(payload) == 6
    assert {
        (row["from_currency"], row["to_currency"])
        for row in payload
    } == {
        ("USD", "EUR"),
        ("USD", "SGD"),
        ("EUR", "USD"),
        ("EUR", "SGD"),
        ("SGD", "USD"),
        ("SGD", "EUR"),
    }
    eur_to_usd = next(
        row["rate"]
        for row in payload
        if row["from_currency"] == "EUR" and row["to_currency"] == "USD"
    )
    assert eur_to_usd == "1.100000"


def test_iter_transaction_batches_yields_expected_records_and_batches() -> None:
    portfolios = [
        {"portfolio_id": "LOAD_RUN1_PF_0001"},
        {"portfolio_id": "LOAD_RUN1_PF_0002"},
    ]
    specs = _build_instrument_specs(run_id="RUN1", instrument_count=3)

    batches = list(
        iter_transaction_batches(
            run_id="RUN1",
            portfolios=portfolios,
            specs=specs,
            trade_date="2026-04-17",
            transaction_batch_size=4,
        )
    )

    assert [len(batch) for batch in batches] == [4, 2]
    flattened = [item for batch in batches for item in batch]
    assert len(flattened) == 6
    assert flattened[0]["transaction_id"] == "LOAD_RUN1_TX_00000001"
    assert flattened[-1]["transaction_id"] == "LOAD_RUN1_TX_00000006"
    assert all(item["quantity"] == "1" for item in flattened)


def test_expected_portfolio_market_value_converts_non_usd_prices() -> None:
    specs = [
        InstrumentSpec(
            security_id="S1",
            currency="USD",
            trade_price=Decimal("10.00"),
            market_price=Decimal("10.10"),
        ),
        InstrumentSpec(
            security_id="S2",
            currency="EUR",
            trade_price=Decimal("20.00"),
            market_price=Decimal("20.20"),
        ),
    ]

    assert expected_portfolio_market_value(specs) == Decimal("32.3200000000")


def test_evaluate_report_flags_tie_out_sample_api_and_log_failures() -> None:
    report = ScenarioReport(
        scenario_name="bank-day-average-load",
        run_id="RUN1",
        terminal_status="failed",
        started_at="2026-04-18T00:00:00Z",
        ended_at="2026-04-18T00:10:00Z",
        duration_seconds=600.0,
        config={
            "portfolio_count": 2,
            "transactions_per_portfolio": 3,
            "transaction_count": 6,
        },
        ingest_phases=[],
        drain_seconds=120.0,
        peak_backlog_jobs=0,
        peak_backlog_age_seconds=0.0,
        peak_replay_pressure_ratio=0.0,
        peak_dlq_events_in_window=0,
        health_samples=[
            HealthSample(
                captured_at="2026-04-18T00:00:10Z",
                backlog_jobs=0,
                backlog_age_seconds=0.0,
                dlq_events_in_window=0,
                replay_pressure_ratio=0.0,
            )
        ],
        database_tie_out=DatabaseTieOut(
            portfolios_count=2,
            instruments_count=3,
            transactions_count=6,
            portfolios_with_snapshots=2,
            snapshots_count=6,
            portfolios_with_position_timeseries=1,
            complete_portfolios=1,
            incomplete_portfolios=1,
            portfolios_waiting_for_snapshots=0,
            snapshot_portfolios_without_position_timeseries=1,
            position_timeseries_count=5,
            portfolios_with_portfolio_timeseries=2,
            portfolios_waiting_for_position_timeseries=1,
            position_timeseries_portfolios_without_portfolio_timeseries=0,
            portfolios_waiting_for_portfolio_timeseries=0,
            portfolio_timeseries_count=2,
            summed_snapshot_quantity="5.0000000000",
            expected_total_quantity="6.0000000000",
            summed_snapshot_market_value="10.0000000000",
            expected_total_market_value="11.0000000000",
            per_security_quantity_min="1.0000000000",
            per_security_quantity_max="2.0000000000",
            pending_valuation_jobs=1,
            processing_valuation_jobs=0,
            open_valuation_jobs=1,
            pending_aggregation_jobs=0,
            processing_aggregation_jobs=0,
            open_aggregation_jobs=0,
            latest_snapshot_materialized_at_utc="2026-04-18T00:01:00Z",
            latest_position_timeseries_materialized_at_utc="2026-04-18T00:02:00Z",
            latest_portfolio_timeseries_materialized_at_utc="2026-04-18T00:03:00Z",
            latest_valuation_job_updated_at_utc="2026-04-18T00:04:00Z",
            latest_aggregation_job_updated_at_utc="2026-04-18T00:05:00Z",
            completed_valuation_jobs_without_position_timeseries=1,
            oldest_completed_valuation_without_position_timeseries_at_utc="2026-04-18T00:01:30Z",
            valuation_to_position_timeseries_latency_sample_count=1,
            valuation_to_position_timeseries_latency_p50_seconds=120.0,
            valuation_to_position_timeseries_latency_p95_seconds=120.0,
            valuation_to_position_timeseries_latency_max_seconds=120.0,
        ),
        sample_portfolios=[
            SamplePortfolioResult(
                portfolio_id="LOAD_RUN1_PF_0001",
                positions_count=2,
                transactions_count=3,
                support_publish_allowed=True,
                support_pending_valuation_jobs=0,
                support_pending_aggregation_jobs=0,
                support_latest_booked_position_snapshot_date="2026-04-17",
                total_market_value="5.0000000000",
                expected_market_value="5.5000000000",
                reconciliation_passed=False,
                reconciliation_finding_count=1,
            )
        ],
        api_probes=[
            ApiProbeResult(
                endpoint="/broken",
                status_code=500,
                latency_ms_samples=[10.0],
                p95_ms=10.0,
                median_ms=10.0,
                check_passed=False,
                failure_detail="boom",
            )
        ],
        log_evidence=[
            LogEvidence(
                container_name="svc",
                error_line_count=2,
                sample_error_lines=["error one"],
            )
        ],
        checks_passed=False,
        failures=[],
    )

    failures = _evaluate_report(report)

    assert any("terminal_status is failed" in failure for failure in failures)
    assert any("complete_portfolios" in failure for failure in failures)
    assert any("portfolios_waiting_for_position_timeseries" in failure for failure in failures)
    assert any("snapshot_portfolios_without_position_timeseries" in failure for failure in failures)
    assert any("portfolios_with_position_timeseries" in failure for failure in failures)
    assert any("position_timeseries_count" in failure for failure in failures)
    assert any("summed_snapshot_quantity" in failure for failure in failures)
    assert any("summed_snapshot_market_value" in failure for failure in failures)
    assert any("per_security_quantity_min" in failure for failure in failures)
    assert any("open_valuation_jobs" in failure for failure in failures)
    assert any("positions_count" in failure for failure in failures)
    assert any("reconciliation findings=1" in failure for failure in failures)
    assert any("API probe failed /broken status=500" in failure for failure in failures)
    assert any("svc logged 2 error/traceback lines" in failure for failure in failures)


def test_finalize_report_marks_aborted_runs_as_failed_and_preserves_partial_evidence() -> None:
    report = _finalize_report(
        args=Namespace(
            scenario_name="bank-day-average-load",
            portfolio_count=2,
            transactions_per_portfolio=2,
            transaction_batch_size=100,
            max_records_per_minute=1000,
            max_requests_per_minute=100,
            host_database_url="postgresql://localhost/test",
            ingestion_base_url="http://localhost:8200",
            query_base_url="http://localhost:8201",
            query_control_base_url="http://localhost:8202",
            event_replay_base_url="http://localhost:8209",
            reconciliation_base_url="http://localhost:8210",
        ),
        run_id="RUN1",
        terminal_status="aborted",
        started_at="2026-04-18T00:00:00Z",
        started_monotonic=0.0,
        resolved_trade_date="2026-04-17",
        ingest_phases=[],
        drain_seconds=0.0,
        health_samples=[],
        tie_out=DatabaseTieOut(
            portfolios_count=0,
            instruments_count=0,
            transactions_count=0,
            portfolios_with_snapshots=0,
            snapshots_count=0,
            portfolios_with_position_timeseries=0,
            complete_portfolios=0,
            incomplete_portfolios=2,
            portfolios_waiting_for_snapshots=2,
            snapshot_portfolios_without_position_timeseries=0,
            position_timeseries_count=0,
            portfolios_with_portfolio_timeseries=0,
            portfolios_waiting_for_position_timeseries=0,
            position_timeseries_portfolios_without_portfolio_timeseries=0,
            portfolios_waiting_for_portfolio_timeseries=0,
            portfolio_timeseries_count=0,
            summed_snapshot_quantity="0.0000000000",
            expected_total_quantity="4.0000000000",
            summed_snapshot_market_value="0.0000000000",
            expected_total_market_value="204.0600000000",
            per_security_quantity_min=None,
            per_security_quantity_max=None,
            pending_valuation_jobs=0,
            processing_valuation_jobs=0,
            open_valuation_jobs=0,
            pending_aggregation_jobs=0,
            processing_aggregation_jobs=0,
            open_aggregation_jobs=0,
            latest_snapshot_materialized_at_utc=None,
            latest_position_timeseries_materialized_at_utc=None,
            latest_portfolio_timeseries_materialized_at_utc=None,
            latest_valuation_job_updated_at_utc=None,
            latest_aggregation_job_updated_at_utc=None,
            completed_valuation_jobs_without_position_timeseries=0,
            oldest_completed_valuation_without_position_timeseries_at_utc=None,
            valuation_to_position_timeseries_latency_sample_count=0,
            valuation_to_position_timeseries_latency_p50_seconds=None,
            valuation_to_position_timeseries_latency_p95_seconds=None,
            valuation_to_position_timeseries_latency_max_seconds=None,
        ),
        sample_portfolios=[],
        api_probes=[],
        log_evidence=[],
        initial_failures=["received SIGINT"],
    )

    assert report.terminal_status == "aborted"
    assert report.checks_passed is False
    assert any("received SIGINT" in failure for failure in report.failures)
    assert any("terminal_status is aborted" in failure for failure in report.failures)
