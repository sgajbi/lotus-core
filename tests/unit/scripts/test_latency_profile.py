from datetime import date
from subprocess import CompletedProcess
from unittest.mock import MagicMock

from scripts.latency_profile import (
    RuntimeContext,
    _cases,
    _enforce_gate,
    _percentile_ms,
    _pick_identifier_from_payload,
    _raise_if_compose_service_failed,
    _resolve_runtime_ids,
    _run_compose_up,
)


def test_percentile_single_sample() -> None:
    assert _percentile_ms([12.5], 95) == 12.5


def test_enforce_gate_detects_budget_and_status_violations() -> None:
    passed, violations = _enforce_gate(
        [
            {
                "name": "ok_case",
                "runs": 10,
                "ok_runs": 10,
                "p95_ms": 99.0,
                "p95_budget_ms": 100.0,
            },
            {
                "name": "status_fail_case",
                "runs": 10,
                "ok_runs": 9,
                "p95_ms": 50.0,
                "p95_budget_ms": 100.0,
            },
            {
                "name": "budget_fail_case",
                "runs": 10,
                "ok_runs": 10,
                "p95_ms": 120.0,
                "p95_budget_ms": 100.0,
            },
        ]
    )
    assert not passed
    assert any("status_fail_case" in v for v in violations)
    assert any("budget_fail_case" in v for v in violations)


def test_pick_identifier_from_payload_nested() -> None:
    payload = {
        "data": {
            "items": [
                {"portfolio_id": "PORT_001"},
            ]
        }
    }
    assert _pick_identifier_from_payload(payload, ("portfolio_id",)) == "PORT_001"


def test_resolve_runtime_ids_overrides_from_catalogs() -> None:
    session = MagicMock()
    lookup_response = MagicMock()
    lookup_response.status_code = 200
    lookup_response.json.return_value = {"items": [{"portfolio_id": "PORT_123"}]}
    not_ready_response = MagicMock()
    not_ready_response.status_code = 404
    ready_response = MagicMock()
    ready_response.status_code = 200
    ready_response.json.return_value = {"business_date": "2026-02-28"}
    benchmark_response = MagicMock()
    benchmark_response.status_code = 200
    benchmark_response.json.return_value = {"benchmarks": [{"benchmark_id": "BMK_ABC"}]}

    def get_side_effect(url: str, timeout: int = 10):  # noqa: ARG001
        if "/lookups/portfolios" in url:
            return lookup_response
        if "DEMO_DPM_EUR_001" in url:
            return not_ready_response
        if "PORT_123" in url:
            return ready_response
        return not_ready_response

    session.get.side_effect = get_side_effect
    session.post.return_value = benchmark_response

    runtime_context = _resolve_runtime_ids(
        session,
        query_base_url="http://localhost:8201",
        query_control_plane_base_url="http://localhost:8202",
        portfolio_id="DEMO_DPM_EUR_001",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        timeout_seconds=5,
    )

    assert runtime_context.portfolio_id == "PORT_123"
    assert runtime_context.benchmark_id == "BMK_ABC"
    assert runtime_context.as_of_date == date(2026, 2, 28)


def test_resolve_runtime_ids_accepts_default_portfolio_when_ready(monkeypatch) -> None:
    session = MagicMock()
    lookup_response = MagicMock()
    lookup_response.status_code = 200
    lookup_response.json.return_value = {"items": [{"portfolio_id": "DEMO_DPM_EUR_001"}]}
    ready_response = MagicMock()
    ready_response.status_code = 200
    ready_response.json.return_value = {"business_date": "2026-03-01"}
    benchmark_response = MagicMock()
    benchmark_response.status_code = 200
    benchmark_response.json.return_value = {"benchmarks": [{"benchmark_id": "BMK_ABC"}]}

    def get_side_effect(url: str, timeout: int = 10):  # noqa: ARG001
        if "/lookups/portfolios" in url:
            return lookup_response
        if "DEMO_DPM_EUR_001" in url:
            return ready_response
        return ready_response

    session.get.side_effect = get_side_effect
    session.post.return_value = benchmark_response
    monkeypatch.setattr("scripts.latency_profile.time.sleep", lambda _: None)

    runtime_context = _resolve_runtime_ids(
        session,
        query_base_url="http://localhost:8201",
        query_control_plane_base_url="http://localhost:8202",
        portfolio_id="DEMO_DPM_EUR_001",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        timeout_seconds=5,
    )

    assert runtime_context.portfolio_id == "DEMO_DPM_EUR_001"
    assert runtime_context.benchmark_id == "BMK_ABC"
    assert runtime_context.as_of_date == date(2026, 3, 1)


def test_resolve_runtime_ids_falls_back_to_portfolio_open_date_when_support_business_date_missing(
    monkeypatch,
) -> None:
    session = MagicMock()
    lookup_response = MagicMock()
    lookup_response.status_code = 200
    lookup_response.json.return_value = {"items": [{"portfolio_id": "PORT_123"}]}
    positions_response = MagicMock()
    positions_response.status_code = 200
    transactions_response = MagicMock()
    transactions_response.status_code = 200
    overview_response = MagicMock()
    overview_response.status_code = 200
    overview_response.json.return_value = {"business_date": None}
    portfolio_response = MagicMock()
    portfolio_response.status_code = 200
    portfolio_response.json.return_value = {"open_date": "2025-01-15"}
    benchmark_response = MagicMock()
    benchmark_response.status_code = 200
    benchmark_response.json.return_value = {"benchmarks": [{"benchmark_id": "BMK_ABC"}]}

    def get_side_effect(url: str, timeout: int = 10):  # noqa: ARG001
        if "/lookups/portfolios" in url:
            return lookup_response
        if "/positions" in url:
            return positions_response
        if "/transactions" in url:
            return transactions_response
        if "/support/portfolios/" in url:
            return overview_response
        if "/portfolios/PORT_123" in url:
            return portfolio_response
        return positions_response

    session.get.side_effect = get_side_effect
    session.post.return_value = benchmark_response
    monkeypatch.setattr("scripts.latency_profile.time.sleep", lambda _: None)

    runtime_context = _resolve_runtime_ids(
        session,
        query_base_url="http://localhost:8201",
        query_control_plane_base_url="http://localhost:8202",
        portfolio_id="DEMO_DPM_EUR_001",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        timeout_seconds=5,
    )

    assert runtime_context.portfolio_id == "PORT_123"
    assert runtime_context.as_of_date == date(2025, 1, 15)


def test_resolve_runtime_ids_raises_when_no_portfolio_becomes_ready(monkeypatch) -> None:
    session = MagicMock()
    lookup_response = MagicMock()
    lookup_response.status_code = 200
    lookup_response.json.return_value = {"items": [{"portfolio_id": "PORT_123"}]}
    not_ready_response = MagicMock()
    not_ready_response.status_code = 404

    def get_side_effect(url: str, timeout: int = 10):  # noqa: ARG001
        if "/lookups/portfolios" in url:
            return lookup_response
        return not_ready_response

    session.get.side_effect = get_side_effect
    session.post.return_value = not_ready_response
    monkeypatch.setattr("scripts.latency_profile.time.sleep", lambda _: None)

    timeline = iter([100.0, 101.0, 106.0])
    monkeypatch.setattr("scripts.latency_profile.time.time", lambda: next(timeline))

    try:
        _resolve_runtime_ids(
            session,
            query_base_url="http://localhost:8201",
            query_control_plane_base_url="http://localhost:8202",
            portfolio_id="DEMO_DPM_EUR_001",
            benchmark_id="BMK_GLOBAL_BALANCED_60_40",
            timeout_seconds=5,
        )
    except RuntimeError as exc:
        assert "could not resolve a query-ready portfolio context" in str(exc)
    else:
        raise AssertionError("Expected _resolve_runtime_ids to raise when no portfolio is ready.")


def test_cases_use_runtime_context_dates_and_identifiers() -> None:
    runtime_context = RuntimeContext(
        portfolio_id="PORT_123",
        benchmark_id="BMK_ABC",
        as_of_date=date(2026, 3, 5),
    )

    cases = _cases(
        ingestion_base_url="http://localhost:8200",
        event_replay_base_url="http://localhost:8209",
        query_base_url="http://localhost:8201",
        query_control_plane_base_url="http://localhost:8202",
        runtime_context=runtime_context,
        include_protected_ops=False,
    )

    analytics_portfolio = next(
        case for case in cases if case.name == "analytics_portfolio_timeseries"
    )
    analytics_position = next(
        case for case in cases if case.name == "analytics_position_timeseries"
    )
    benchmark_series = next(case for case in cases if case.name == "benchmark_market_series")

    assert "/portfolios/PORT_123/" in analytics_portfolio.url
    assert analytics_portfolio.payload["as_of_date"] == "2026-03-05"
    assert analytics_position.payload["as_of_date"] == "2026-03-05"
    assert "/benchmarks/BMK_ABC/market-series" in benchmark_series.url
    assert benchmark_series.payload["as_of_date"] == "2026-03-05"
    assert benchmark_series.payload["window"] == {
        "start_date": "2025-12-05",
        "end_date": "2026-03-05",
    }


def test_context_timeout_must_not_be_shorter_than_ready_timeout() -> None:
    ready_timeout_seconds = 180
    context_timeout_seconds = 120

    assert max(context_timeout_seconds, ready_timeout_seconds) == 180


def test_raise_if_compose_service_failed_ignores_running_service(monkeypatch) -> None:
    def _fake_run(cmd, check=False, capture_output=False, text=False):  # noqa: ARG001
        if cmd[:5] == ["docker", "compose", "ps", "-a", "-q"]:
            return CompletedProcess(cmd, 0, stdout="container-123\n", stderr="")
        return CompletedProcess(cmd, 0, stdout="running|0\n", stderr="")

    monkeypatch.setattr("scripts.latency_profile.subprocess.run", _fake_run)

    _raise_if_compose_service_failed("demo_data_loader")


def test_raise_if_compose_service_failed_raises_on_failure(monkeypatch) -> None:
    def _fake_run(cmd, check=False, capture_output=False, text=False):  # noqa: ARG001
        if cmd[:5] == ["docker", "compose", "ps", "-a", "-q"]:
            return CompletedProcess(cmd, 0, stdout="container-123\n", stderr="")
        return CompletedProcess(cmd, 0, stdout="exited|1\n", stderr="")

    monkeypatch.setattr("scripts.latency_profile.subprocess.run", _fake_run)

    try:
        _raise_if_compose_service_failed("demo_data_loader")
    except RuntimeError as exc:
        assert "exited with status 1" in str(exc)
    else:
        raise AssertionError("Expected _raise_if_compose_service_failed to raise.")


def test_run_compose_up_limits_started_services(monkeypatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(cmd, check=False):  # noqa: ARG001
        calls.append(cmd)
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("scripts.latency_profile.subprocess.run", _fake_run)

    _run_compose_up(build=False)

    assert calls == [
        [
            "docker",
            "compose",
            "up",
            "-d",
            "ingestion_service",
            "query_service",
            "query_control_plane_service",
            "event_replay_service",
            "persistence_service",
            "position_calculator_service",
            "pipeline_orchestrator_service",
            "valuation_orchestrator_service",
            "position_valuation_calculator",
            "timeseries_generator_service",
            "portfolio_aggregation_service",
            "demo_data_loader",
        ]
    ]
