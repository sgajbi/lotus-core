from argparse import Namespace
from decimal import Decimal
from subprocess import CalledProcessError, CompletedProcess

import pytest

from scripts.operations import bank_day_load_scenario
from scripts.operations.bank_day_load_scenario import (
    LOG_SERVICE_NAMES,
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
    _wait_for_cycle_completion,
    expected_portfolio_market_value,
    iter_transaction_batches,
)
from scripts.operations.performance.derived_state_resource_monitor import (
    DerivedStateResourceEvidence,
)
from scripts.operations.transaction_processing_load_support import (
    CostProcessingExecutionEvidence,
    CostProcessingHistogramEvidence,
    CostProcessingRuntimeEvidence,
    DatabaseOperationEvidence,
    TransactionProcessingOperationEvidence,
)


def test_log_evidence_uses_the_combined_transaction_processing_runtime() -> None:
    assert "portfolio_transaction_processing_service" in LOG_SERVICE_NAMES
    assert not any("calculator_service" in name for name in LOG_SERVICE_NAMES)


def test_operation_evidence_collection_preserves_bounded_stage_totals(monkeypatch) -> None:
    expected = [
        TransactionProcessingOperationEvidence(
            stage="cost",
            outcome="succeeded",
            operation_count=100,
            duration_observation_count=100,
            total_duration_seconds=25.0,
            average_duration_seconds=0.25,
        )
    ]
    monkeypatch.setattr(
        bank_day_load_scenario,
        "transaction_processing_operation_evidence",
        lambda **_kwargs: expected,
    )

    evidence, failures = (
        bank_day_load_scenario._safe_collect_transaction_processing_operation_evidence(
            transaction_processing_base_url="http://localhost:8090"
        )
    )

    assert evidence == expected
    assert failures == []


def test_operation_evidence_collection_fails_closed_on_empty_scrape(monkeypatch) -> None:
    monkeypatch.setattr(
        bank_day_load_scenario,
        "transaction_processing_operation_evidence",
        lambda **_kwargs: [],
    )

    evidence, failures = (
        bank_day_load_scenario._safe_collect_transaction_processing_operation_evidence(
            transaction_processing_base_url="http://localhost:8090"
        )
    )

    assert evidence == []
    assert failures == ["transaction-processing operation metrics returned no bounded samples"]


def test_cost_runtime_evidence_collection_preserves_existing_metrics(monkeypatch) -> None:
    histogram = CostProcessingHistogramEvidence(
        metric_name="recalculation_duration_seconds",
        cost_basis_method=None,
        observation_count=100,
        total=5.0,
        average=0.05,
    )
    expected = CostProcessingRuntimeEvidence(
        executions=[
            CostProcessingExecutionEvidence(
                mode="full_rebuild",
                cost_basis_method="FIFO",
                operation_count=100,
            )
        ],
        recalculation_duration_seconds=histogram,
        recalculation_depth=CostProcessingHistogramEvidence(
            metric_name="recalculation_depth",
            cost_basis_method=None,
            observation_count=100,
            total=100.0,
            average=1.0,
        ),
        restored_open_lots=[],
    )
    monkeypatch.setattr(
        bank_day_load_scenario,
        "cost_processing_runtime_evidence",
        lambda **_kwargs: expected,
    )

    evidence, failures = bank_day_load_scenario._safe_collect_cost_processing_runtime_evidence(
        transaction_processing_base_url="http://localhost:8090"
    )

    assert evidence == expected
    assert failures == []


def test_cost_runtime_evidence_collection_rejects_missing_recalculation_metrics(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bank_day_load_scenario,
        "cost_processing_runtime_evidence",
        lambda **_kwargs: CostProcessingRuntimeEvidence(
            executions=[],
            recalculation_duration_seconds=None,
            recalculation_depth=None,
            restored_open_lots=[],
        ),
    )

    evidence, failures = bank_day_load_scenario._safe_collect_cost_processing_runtime_evidence(
        transaction_processing_base_url="http://localhost:8090"
    )

    assert evidence is None
    assert failures == ["cost-processing runtime metrics returned incomplete bounded samples"]


def test_database_operation_evidence_collection_preserves_bounded_samples(
    monkeypatch,
) -> None:
    expected = [
        DatabaseOperationEvidence(
            repository="CostRepository",
            method="load",
            observation_count=100,
            total_duration_seconds=25.0,
            average_duration_seconds=0.25,
        )
    ]
    monkeypatch.setattr(
        bank_day_load_scenario,
        "database_operation_evidence",
        lambda **_kwargs: expected,
    )

    evidence, failures = bank_day_load_scenario._safe_collect_database_operation_evidence(
        transaction_processing_base_url="http://localhost:8090"
    )

    assert evidence == expected
    assert failures == []


def test_database_operation_evidence_collection_fails_closed_on_empty_scrape(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bank_day_load_scenario,
        "database_operation_evidence",
        lambda **_kwargs: [],
    )

    evidence, failures = bank_day_load_scenario._safe_collect_database_operation_evidence(
        transaction_processing_base_url="http://localhost:8090"
    )

    assert evidence == []
    assert failures == ["database operation metrics returned no bounded repository/method samples"]


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
    assert {(row["from_currency"], row["to_currency"]) for row in payload} == {
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


def test_cycle_completion_waits_until_durable_outbox_is_empty(monkeypatch) -> None:
    captured: dict[str, str] = {}
    complete_row: dict[str, object] = {
        "portfolios_count": 2,
        "transactions_count": 4,
        "failed_valuation_jobs": 0,
        "failed_aggregation_jobs": 0,
        "failed_outbox_events": 0,
        "snapshots_count": 4,
        "completed_valuation_jobs_without_snapshots": 0,
        "position_timeseries_count": 4,
        "portfolio_timeseries_count": 2,
        "pending_valuation_jobs": 0,
        "processing_valuation_jobs": 0,
        "pending_aggregation_jobs": 0,
        "processing_aggregation_jobs": 0,
        "pending_outbox_events": 0,
    }
    rows: list[dict[str, object]] = [
        {**complete_row, "pending_outbox_events": 1},
        complete_row,
    ]

    def fake_db_row(_engine, query: str, _params: dict[str, object]) -> dict[str, object]:
        captured["query"] = query
        return rows.pop(0)

    monkeypatch.setattr(bank_day_load_scenario, "_db_row", fake_db_row)
    monkeypatch.setattr(bank_day_load_scenario.time, "sleep", lambda _seconds: None)

    elapsed = _wait_for_cycle_completion(
        engine=object(),
        run_id="RUN1",
        trade_date="2026-07-15",
        portfolio_count=2,
        transaction_count=4,
        timeout_seconds=1,
    )

    assert elapsed >= 0
    assert rows == []
    assert "pending_outbox_events" in captured["query"]


def test_cycle_completion_fails_fast_for_completed_valuation_without_snapshot(
    monkeypatch,
) -> None:
    terminal_inconsistency: dict[str, object] = {
        "portfolios_count": 1,
        "transactions_count": 2,
        "failed_valuation_jobs": 0,
        "failed_aggregation_jobs": 0,
        "failed_outbox_events": 0,
        "snapshots_count": 0,
        "completed_valuation_jobs_without_snapshots": 2,
        "position_timeseries_count": 0,
        "portfolio_timeseries_count": 0,
        "pending_valuation_jobs": 0,
        "processing_valuation_jobs": 0,
        "pending_aggregation_jobs": 0,
        "processing_aggregation_jobs": 0,
        "pending_outbox_events": 0,
    }
    monkeypatch.setattr(
        bank_day_load_scenario,
        "_db_row",
        lambda _engine, _query, _params: terminal_inconsistency,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "terminal valuation jobs without atomic snapshot side effects: "
            "completed_valuation_jobs_without_snapshots=2"
        ),
    ):
        _wait_for_cycle_completion(
            engine=object(),
            run_id="RUN1",
            trade_date="2026-07-17",
            portfolio_count=1,
            transaction_count=2,
            timeout_seconds=60,
        )


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
    assert expected_portfolio_market_value(
        specs,
        {("EUR", "USD"): Decimal("1.155000")},
    ) == Decimal("33.4310000000")


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
            "transaction_processing_operation_evidence_required": True,
            "cost_processing_runtime_evidence_required": True,
            "database_operation_evidence_required": True,
            "derived_state_resource_evidence_required": True,
            "market_price_correction_multiplier": "1.05",
            "fx_rate_correction_multiplier": "1.05",
            "restart_valuation_orchestrator_during_fx_correction": True,
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
            valuation_to_position_timeseries_latency_p99_seconds=120.0,
            valuation_to_position_timeseries_latency_max_seconds=120.0,
            position_to_portfolio_timeseries_latency_sample_count=1,
            position_to_portfolio_timeseries_latency_p50_seconds=30.0,
            position_to_portfolio_timeseries_latency_p95_seconds=30.0,
            position_to_portfolio_timeseries_latency_p99_seconds=30.0,
            position_to_portfolio_timeseries_latency_max_seconds=30.0,
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
        derived_state_resource_evidence=None,
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
    assert any(
        "valuation_to_position_timeseries_latency_sample_count" in failure for failure in failures
    )
    assert any(
        "position_to_portfolio_timeseries_latency_sample_count" in failure for failure in failures
    )
    assert any("positions_count" in failure for failure in failures)
    assert any("reconciliation findings=1" in failure for failure in failures)
    assert any("API probe failed /broken status=500" in failure for failure in failures)
    assert any("svc logged 2 error/traceback lines" in failure for failure in failures)
    assert "transaction-processing operation evidence has no samples" in failures
    assert "cost-processing runtime evidence is incomplete" in failures
    assert any("derived-state resource evidence has no samples" in failure for failure in failures)
    assert any(
        "market price correction has no completed drain evidence" in failure for failure in failures
    )
    assert any(
        "FX rate correction has no completed drain evidence" in failure for failure in failures
    )
    assert any(
        "FX rate correction has no measured restart recovery evidence" in failure
        for failure in failures
    )


def test_source_provenance_records_revision_and_dirty_tree_state(monkeypatch) -> None:
    responses = iter(
        (
            CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout=" M changed.py\n", stderr=""),
        )
    )

    monkeypatch.setattr(
        bank_day_load_scenario.subprocess,
        "run",
        lambda *args, **kwargs: next(responses),
    )

    assert bank_day_load_scenario._source_provenance() == {
        "source_revision": "abc123",
        "source_tree_state": "dirty",
    }


def test_source_provenance_records_revision_and_clean_tree_state(monkeypatch) -> None:
    responses = iter(
        (
            CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        )
    )

    monkeypatch.setattr(
        bank_day_load_scenario.subprocess,
        "run",
        lambda *args, **kwargs: next(responses),
    )

    assert bank_day_load_scenario._source_provenance() == {
        "source_revision": "abc123",
        "source_tree_state": "clean",
    }


def test_source_provenance_fails_closed_when_git_metadata_is_unavailable(monkeypatch) -> None:
    def raise_git_error(*args, **kwargs):
        raise CalledProcessError(returncode=128, cmd=args[0])

    monkeypatch.setattr(bank_day_load_scenario.subprocess, "run", raise_git_error)

    assert bank_day_load_scenario._source_provenance() == {
        "source_revision": None,
        "source_tree_state": "unavailable",
    }


def test_finalize_report_marks_aborted_runs_as_failed_and_preserves_partial_evidence(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bank_day_load_scenario,
        "_source_provenance",
        lambda: {
            "source_revision": "abc123",
            "source_tree_state": "clean",
        },
    )
    report = _finalize_report(
        args=Namespace(
            scenario_name="bank-day-average-load",
            evidence_classification="diagnostic",
            portfolio_count=2,
            transactions_per_portfolio=2,
            transaction_batch_size=100,
            business_date_count=1,
            max_records_per_minute=1000,
            max_requests_per_minute=100,
            host_database_url=(
                "postgresql://load_user:load_password@localhost:5432/test?sslmode=disable"
            ),
            ingestion_base_url="http://localhost:8200",
            query_base_url="http://localhost:8201",
            query_control_base_url="http://localhost:8202",
            event_replay_base_url="http://localhost:8209",
            reconciliation_base_url="http://localhost:8210",
            resource_poll_interval_seconds=5.0,
            derived_state_service="portfolio_derived_state_service",
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
            valuation_to_position_timeseries_latency_p99_seconds=None,
            valuation_to_position_timeseries_latency_max_seconds=None,
            position_to_portfolio_timeseries_latency_sample_count=0,
            position_to_portfolio_timeseries_latency_p50_seconds=None,
            position_to_portfolio_timeseries_latency_p95_seconds=None,
            position_to_portfolio_timeseries_latency_p99_seconds=None,
            position_to_portfolio_timeseries_latency_max_seconds=None,
        ),
        sample_portfolios=[],
        api_probes=[],
        log_evidence=[],
        initial_failures=["received SIGINT"],
        derived_state_resource_evidence=DerivedStateResourceEvidence(
            sample_count=2,
            sampling_error_count=0,
            sampling_error_types=(),
            peak_database_total_connections=12,
            peak_database_active_connections=5,
            peak_database_idle_in_transaction_connections=0,
            peak_database_lock_waiters=0,
            peak_database_blocked_sessions=0,
            peak_database_connection_utilization_percent=12.0,
            peak_runtime_cpu_percent=40.0,
            peak_runtime_memory_usage_bytes=268435456,
            peak_runtime_memory_utilization_percent=25.0,
            peak_outbox_pending_events=120,
            peak_outbox_oldest_pending_age_seconds=30.0,
            peak_outbox_retry_eligible_pending_events=120,
            peak_outbox_retry_waiting_pending_events=0,
            peak_outbox_failed_events=0,
            final_outbox_pending_events=0,
            final_outbox_processed_events=500,
            final_outbox_failed_events=0,
            final_outbox_pending_events_by_topic=(),
            final_outbox_created_events_by_topic=(("transactions.persisted", 500),),
        ),
    )

    assert report.terminal_status == "aborted"
    assert report.checks_passed is False
    assert any("received SIGINT" in failure for failure in report.failures)
    assert any("terminal_status is aborted" in failure for failure in report.failures)
    assert report.derived_state_resource_evidence is not None
    assert report.derived_state_resource_evidence.peak_runtime_cpu_percent == 40.0
    assert report.derived_state_resource_evidence.final_outbox_pending_events == 0
    assert report.config["database_target"] == {
        "backend": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database": "test",
    }
    assert report.config["source_revision"] == "abc123"
    assert report.config["source_tree_state"] == "clean"
    assert report.config["transaction_processing_base_url"] == "http://localhost:8090"
    assert report.config["transaction_processing_operation_evidence_required"] is True
    assert report.config["cost_processing_runtime_evidence_required"] is True
    assert report.config["database_operation_evidence_required"] is True
    assert "load_user" not in str(report.config)
    assert "load_password" not in str(report.config)
    assert "sslmode" not in str(report.config)


def test_database_tie_out_measures_both_materialization_stages_with_upsert_timestamps(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_db_row(_engine, query: str, params: dict[str, object]) -> dict[str, object]:
        captured["query"] = query
        captured["params"] = params
        return {
            "portfolios_count": 1,
            "instruments_count": 1,
            "transactions_count": 1,
            "portfolios_with_snapshots": 1,
            "snapshots_count": 1,
            "portfolios_with_position_timeseries": 1,
            "position_timeseries_count": 1,
            "portfolios_with_portfolio_timeseries": 1,
            "portfolio_timeseries_count": 1,
            "summed_snapshot_quantity": Decimal("1"),
            "summed_snapshot_market_value": Decimal("50.5"),
            "per_security_quantity_min": Decimal("1"),
            "per_security_quantity_max": Decimal("1"),
            "pending_valuation_jobs": 0,
            "processing_valuation_jobs": 0,
            "completed_valuation_jobs": 1,
            "valuation_job_attempt_count_min": 2,
            "valuation_job_attempt_count_max": 2,
            "valuation_jobs_with_repeated_processing": 0,
            "pending_aggregation_jobs": 0,
            "processing_aggregation_jobs": 0,
            "latest_snapshot_materialized_at_utc": None,
            "latest_position_timeseries_materialized_at_utc": None,
            "latest_portfolio_timeseries_materialized_at_utc": None,
            "latest_valuation_job_updated_at_utc": None,
            "latest_aggregation_job_updated_at_utc": None,
            "completed_valuation_jobs_without_position_timeseries": 0,
            "oldest_completed_valuation_without_position_timeseries_at_utc": None,
            "valuation_to_position_timeseries_latency_sample_count": 1,
            "valuation_to_position_timeseries_latency_p50_seconds": Decimal("0.5"),
            "valuation_to_position_timeseries_latency_p95_seconds": Decimal("0.9"),
            "valuation_to_position_timeseries_latency_p99_seconds": Decimal("0.99"),
            "valuation_to_position_timeseries_latency_max_seconds": Decimal("1.0"),
            "position_to_portfolio_timeseries_latency_sample_count": 1,
            "position_to_portfolio_timeseries_latency_p50_seconds": Decimal("0.25"),
            "position_to_portfolio_timeseries_latency_p95_seconds": Decimal("0.45"),
            "position_to_portfolio_timeseries_latency_p99_seconds": Decimal("0.49"),
            "position_to_portfolio_timeseries_latency_max_seconds": Decimal("0.5"),
        }

    monkeypatch.setattr(bank_day_load_scenario, "_db_row", fake_db_row)
    specs = _build_instrument_specs(run_id="RUN1", instrument_count=1)

    tie_out = bank_day_load_scenario._build_database_tie_out(
        engine=object(),
        run_id="RUN1",
        trade_date="2026-04-17",
        portfolio_count=1,
        specs=specs,
    )

    query = str(captured["query"])
    assert "valuation_to_position_latencies AS" in query
    assert "pts.updated_at - pvj.updated_at" in query
    assert "position_materialization_completion AS" in query
    assert "max(updated_at) AS positions_materialized_at" in query
    assert "pfts.updated_at - pmc.positions_materialized_at" in query
    assert "attempt_count > 2" in query
    assert query.count("percentile_cont(0.99)") == 2
    assert captured["params"] == {
        "portfolio_pattern": "LOAD_RUN1_PF_%",
        "transaction_pattern": "LOAD_RUN1_TX_%",
        "security_pattern": "LOAD_RUN1_SEC_%",
        "trade_date": "2026-04-17",
    }
    assert tie_out.valuation_to_position_timeseries_latency_p99_seconds == 0.99
    assert tie_out.position_to_portfolio_timeseries_latency_sample_count == 1
    assert tie_out.position_to_portfolio_timeseries_latency_p99_seconds == 0.49
    assert tie_out.completed_valuation_jobs == 1
    assert tie_out.valuation_job_attempt_count_min == 2
    assert tie_out.valuation_job_attempt_count_max == 2
    assert tie_out.valuation_jobs_with_repeated_processing == 0


def test_evaluate_report_rejects_baseline_valuation_reprocessing() -> None:
    report = ScenarioReport(
        scenario_name="bank-day-average-load",
        run_id="RUN1",
        terminal_status="complete",
        started_at="2026-04-18T00:00:00Z",
        ended_at="2026-04-18T00:01:00Z",
        duration_seconds=60.0,
        config={
            "portfolio_count": 0,
            "transactions_per_portfolio": 0,
            "transaction_count": 0,
            "derived_state_resource_evidence_required": False,
            "market_price_correction_multiplier": None,
            "fx_rate_correction_multiplier": None,
            "restart_valuation_orchestrator_during_fx_correction": False,
        },
        ingest_phases=[],
        drain_seconds=0.0,
        peak_backlog_jobs=0,
        peak_backlog_age_seconds=0.0,
        peak_replay_pressure_ratio=0.0,
        peak_dlq_events_in_window=0,
        health_samples=[],
        database_tie_out=DatabaseTieOut(
            portfolios_count=0,
            instruments_count=0,
            transactions_count=0,
            portfolios_with_snapshots=0,
            snapshots_count=0,
            portfolios_with_position_timeseries=0,
            complete_portfolios=0,
            incomplete_portfolios=0,
            portfolios_waiting_for_snapshots=0,
            snapshot_portfolios_without_position_timeseries=0,
            position_timeseries_count=0,
            portfolios_with_portfolio_timeseries=0,
            portfolios_waiting_for_position_timeseries=0,
            position_timeseries_portfolios_without_portfolio_timeseries=0,
            portfolios_waiting_for_portfolio_timeseries=0,
            portfolio_timeseries_count=0,
            summed_snapshot_quantity="0.0000000000",
            expected_total_quantity="0.0000000000",
            summed_snapshot_market_value="0.0000000000",
            expected_total_market_value="0.0000000000",
            per_security_quantity_min="0.0000000000",
            per_security_quantity_max="0.0000000000",
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
            valuation_to_position_timeseries_latency_p99_seconds=None,
            valuation_to_position_timeseries_latency_max_seconds=None,
            position_to_portfolio_timeseries_latency_sample_count=0,
            position_to_portfolio_timeseries_latency_p50_seconds=None,
            position_to_portfolio_timeseries_latency_p95_seconds=None,
            position_to_portfolio_timeseries_latency_p99_seconds=None,
            position_to_portfolio_timeseries_latency_max_seconds=None,
            completed_valuation_jobs=0,
            valuation_job_attempt_count_min=2,
            valuation_job_attempt_count_max=4,
            valuation_jobs_with_repeated_processing=1,
        ),
        sample_portfolios=[],
        api_probes=[],
        log_evidence=[],
        checks_passed=False,
        failures=[],
        derived_state_resource_evidence=DerivedStateResourceEvidence(
            sample_count=1,
            sampling_error_count=0,
            sampling_error_types=(),
            peak_database_total_connections=1,
            peak_database_active_connections=0,
            peak_database_idle_in_transaction_connections=0,
            peak_database_lock_waiters=0,
            peak_database_blocked_sessions=0,
            peak_database_connection_utilization_percent=1.0,
            peak_runtime_cpu_percent=1.0,
            peak_runtime_memory_usage_bytes=1,
            peak_runtime_memory_utilization_percent=1.0,
            peak_outbox_pending_events=0,
            peak_outbox_oldest_pending_age_seconds=0.0,
            peak_outbox_retry_eligible_pending_events=0,
            peak_outbox_retry_waiting_pending_events=0,
            peak_outbox_failed_events=0,
            final_outbox_pending_events=0,
            final_outbox_processed_events=1,
            final_outbox_failed_events=0,
            final_outbox_pending_events_by_topic=(),
            final_outbox_created_events_by_topic=(("valuation.snapshot.persisted", 1),),
        ),
    )

    failures = _evaluate_report(report)

    assert "valuation_job_attempt_count_max 4 != expected 2" in failures
    assert "valuation_jobs_with_repeated_processing 1 != expected 0" in failures
    assert "valuation_snapshot_event_count 1 != expected 0" in failures
