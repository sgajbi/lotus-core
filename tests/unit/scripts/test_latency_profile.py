from subprocess import CompletedProcess
from unittest.mock import MagicMock

from scripts.latency_profile import (
    _enforce_gate,
    _percentile_ms,
    _pick_identifier_from_payload,
    _raise_if_compose_service_failed,
    _resolve_runtime_ids,
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

    portfolio_id, benchmark_id = _resolve_runtime_ids(
        session,
        query_base_url="http://localhost:8201",
        query_control_plane_base_url="http://localhost:8202",
        portfolio_id="DEMO_DPM_EUR_001",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        timeout_seconds=5,
    )

    assert portfolio_id == "PORT_123"
    assert benchmark_id == "BMK_ABC"


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
