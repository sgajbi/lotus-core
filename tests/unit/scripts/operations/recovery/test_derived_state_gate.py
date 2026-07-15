"""Unit proof for the unified portfolio derived-state recovery gate."""

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.operations.recovery import derived_state_gate
from scripts.operations.recovery.derived_state_gate import (
    DerivedStateCounts,
    DerivedStateRecoveryResult,
    evaluate_recovery,
    prepare_managed_run,
    seed_market_prices,
    wait_for_full_recovery,
    write_report,
)


def test_recovery_evaluation_accepts_exact_drain_and_rejects_partial_state() -> None:
    complete = DerivedStateCounts(10, 10, 1, 0, 0)

    assert (
        evaluate_recovery(
            expected_position_count=10,
            baseline_consumer_lag=0,
            peak_consumer_lag=10,
            consumer_lag_after_recovery=0,
            recovery_seconds=4.5,
            max_recovery_seconds=30,
            counts=complete,
            reconciliation_finding_count=0,
            dlq_events_added=0,
        )
        == ()
    )

    failures = evaluate_recovery(
        expected_position_count=10,
        baseline_consumer_lag=0,
        peak_consumer_lag=4,
        consumer_lag_after_recovery=2,
        recovery_seconds=None,
        max_recovery_seconds=30,
        counts=DerivedStateCounts(10, 9, 0, 1, 1),
        reconciliation_finding_count=2,
        dlq_events_added=1,
    )

    assert any("lag growth 4" in failure for failure in failures)
    assert any("did not fully recover" in failure for failure in failures)
    assert any("position_timeseries_count 9" in failure for failure in failures)
    assert any("open_aggregation_job_count 1" in failure for failure in failures)
    assert any("reconciliation returned 2" in failure for failure in failures)
    assert any("added 1 DLQ" in failure for failure in failures)


def test_wait_for_full_recovery_requires_outputs_queues_and_lag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_counts = iter(
        (
            DerivedStateCounts(3, 2, 0, 1, 1),
            DerivedStateCounts(3, 3, 1, 0, 0),
        )
    )
    observed_lags = iter((3, 0))
    elapsed = 0.0

    monkeypatch.setattr(
        derived_state_gate,
        "derived_state_counts",
        lambda **_kwargs: next(observed_counts),
    )
    monkeypatch.setattr(
        derived_state_gate,
        "consumer_lag",
        lambda **_kwargs: next(observed_lags),
    )

    def clock() -> float:
        return elapsed

    def sleeper(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    recovery_seconds, counts, lag = wait_for_full_recovery(
        store=object(),
        engine=object(),  # type: ignore[arg-type]
        consumer_group="timeseries_generator_group_positions",
        topic="valuation.snapshot.persisted",
        baseline_lag=0,
        portfolio_id="P1",
        business_date="2026-07-15",
        expected_position_count=3,
        timeout_seconds=5,
        clock=clock,
        sleeper=sleeper,
    )

    assert recovery_seconds == 1.0
    assert counts == DerivedStateCounts(3, 3, 1, 0, 0)
    assert lag == 0


def test_market_price_seed_uses_exact_instrument_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> object:
        captured.update(url=url, json=json, timeout=timeout)
        return SimpleNamespace(status_code=202, text="")

    monkeypatch.setattr(derived_state_gate.requests, "post", fake_post)
    monkeypatch.setattr(
        derived_state_gate,
        "wait_for_database_count",
        lambda **kwargs: captured.update(wait=kwargs),
    )

    seed_market_prices(
        engine=object(),  # type: ignore[arg-type]
        ingestion_base_url="http://localhost:8200",
        security_prefix="DR_RUN_SEC",
        business_date="2026-07-15",
        instrument_count=3,
        timeout_seconds=30,
    )

    payload = captured["json"]
    assert isinstance(payload, dict)
    prices = payload["market_prices"]
    assert isinstance(prices, list)
    assert [price["security_id"] for price in prices] == [
        "DR_RUN_SEC_000",
        "DR_RUN_SEC_001",
        "DR_RUN_SEC_002",
    ]
    assert all(price["currency"] == "USD" for price in prices)
    wait = captured["wait"]
    assert isinstance(wait, dict)
    assert wait["expected"] == 3
    assert wait["params"] == {
        "pattern": "DR_RUN_SEC_%",
        "business_date": "2026-07-15",
    }


def test_managed_run_uses_unified_runtime_and_generated_endpoint_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()
    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.prepare_managed_compose_run",
        lambda **kwargs: captured.update(kwargs) or sentinel,
    )
    args = Namespace(
        compose_file="docker-compose.yml",
        compose_project_name=None,
        skip_compose=False,
        build=True,
        output_dir="output/task-runs",
        keep_stack_up=False,
        ingestion_base_url=None,
        event_replay_base_url=None,
        derived_state_base_url="http://localhost:18085",
        reconciliation_base_url=None,
        host_database_url=None,
    )

    result = prepare_managed_run(args=args, repo_root=tmp_path)

    assert result is sentinel
    services = captured["services"]
    assert isinstance(services, tuple)
    assert "portfolio_derived_state_service" in services
    assert "timeseries_generator_service" not in services
    assert "portfolio_aggregation_service" not in services
    assert captured["endpoint_urls"] == {
        "E2E_INGESTION_URL": None,
        "E2E_EVENT_REPLAY_URL": None,
        "E2E_PORTFOLIO_DERIVED_STATE_URL": "http://localhost:18085",
        "E2E_FINANCIAL_RECONCILIATION_URL": None,
        "HOST_DATABASE_URL": None,
    }


def test_recovery_report_preserves_counts_and_failure_evidence(tmp_path: Path) -> None:
    result = DerivedStateRecoveryResult(
        run_id="20260715T000000Z",
        started_at="2026-07-15T00:00:00+00:00",
        ended_at="2026-07-15T00:00:10+00:00",
        interruption_service="portfolio_derived_state_service",
        interruption_container_id="container-id",
        requested_interruption_seconds=5,
        actual_interruption_seconds=5.1,
        source_topic="valuation.snapshot.persisted",
        consumer_group="timeseries_generator_group_positions",
        expected_position_count=3,
        source_snapshot_materialization_seconds=1.2,
        baseline_consumer_lag=0,
        peak_consumer_lag_during_interruption=3,
        consumer_lag_growth=3,
        consumer_lag_after_recovery=1,
        recovery_seconds=None,
        counts=DerivedStateCounts(3, 2, 0, 1, 1),
        reconciliation_finding_count=1,
        dlq_events_added_during_recovery=0,
        checks_passed=False,
        failed_checks=("position output incomplete",),
    )

    json_path, markdown_path = write_report(output_dir=tmp_path, result=result)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["counts"]["position_timeseries_count"] == 2
    assert payload["failed_checks"] == ["position output incomplete"]
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Derived-State Recovery Gate" in markdown
    assert "position output incomplete" in markdown
