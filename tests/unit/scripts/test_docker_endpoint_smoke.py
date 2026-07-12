from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from scripts.validation import docker_endpoint_smoke
from scripts.validation.docker_endpoint_smoke import (
    SMOKE_CSV_TRANSACTION_ID,
    SMOKE_INSTRUMENT_ID,
    SMOKE_ISIN,
    SMOKE_PORTFOLIO_ID,
    SMOKE_SECURITY_ID,
    SMOKE_TRANSACTION_ID,
    SMOKE_TRANSACTION_ID_2,
    _bounded_smoke_window_query,
    _resolve_postgres_container,
    _wait_expected_status,
    build_smoke_cleanup_sql,
)


def test_docker_endpoint_smoke_uses_deterministic_identifiers():
    assert SMOKE_PORTFOLIO_ID == "PORT_SMOKE_CANONICAL"
    assert SMOKE_SECURITY_ID == "SEC_SMOKE_CANONICAL"
    assert SMOKE_INSTRUMENT_ID == "INST_SMOKE_CANONICAL"
    assert SMOKE_TRANSACTION_ID == "TX_SMOKE_CANONICAL"
    assert SMOKE_TRANSACTION_ID_2 == "TX2_SMOKE_CANONICAL"
    assert SMOKE_CSV_TRANSACTION_ID == "TXUP_SMOKE_CANONICAL"
    assert SMOKE_ISIN == "US000SMOKE01"


def test_docker_endpoint_smoke_cleanup_sql_purges_legacy_smoke_rows():
    sql = build_smoke_cleanup_sql()

    assert "delete from transactions where portfolio_id like 'PORT_SMOKE_%';" in sql
    assert "delete from portfolios where portfolio_id like 'PORT_SMOKE_%';" in sql
    assert "delete from market_prices where security_id like 'SEC_SMOKE_%';" in sql
    assert "delete from transaction_costs where transaction_id like 'TX%_SMOKE_%';" in sql


def test_docker_endpoint_smoke_uses_bounded_raw_series_window():
    assert _bounded_smoke_window_query("2026-07-06") == (
        "start_date=2026-07-06&end_date=2026-07-06"
    )


def test_wait_expected_status_retries_until_endpoint_is_ready(monkeypatch: pytest.MonkeyPatch):
    responses = iter(
        [
            SimpleNamespace(status_code=404),
            SimpleNamespace(status_code=404),
            SimpleNamespace(status_code=200),
        ]
    )
    get_mock = Mock(side_effect=lambda *args, **kwargs: next(responses))
    now = iter([0, 1, 2, 3])

    monkeypatch.setattr("scripts.validation.docker_endpoint_smoke.requests.get", get_mock)
    monkeypatch.setattr(
        "scripts.validation.docker_endpoint_smoke.time.sleep", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr("scripts.validation.docker_endpoint_smoke.time.time", lambda: next(now))

    _wait_expected_status("http://query/ready-endpoint", {200}, timeout_seconds=5)

    assert get_mock.call_count == 3


def test_wait_expected_status_raises_with_last_status_context(
    monkeypatch: pytest.MonkeyPatch,
):
    get_mock = Mock(return_value=SimpleNamespace(status_code=404))
    now = iter([0, 1, 2, 3])

    monkeypatch.setattr("scripts.validation.docker_endpoint_smoke.requests.get", get_mock)
    monkeypatch.setattr(
        "scripts.validation.docker_endpoint_smoke.time.sleep", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr("scripts.validation.docker_endpoint_smoke.time.time", lambda: next(now))

    with pytest.raises(TimeoutError, match="last_status=404"):
        _wait_expected_status("http://query/missing-endpoint", {200}, timeout_seconds=2)


def test_resolve_postgres_container_uses_managed_project_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    managed_run = MagicMock()
    managed_run.compose_command.return_value = [
        "docker",
        "compose",
        "-p",
        "lotus-e2e-smoke-1234",
        "ps",
        "-q",
        "postgres",
    ]
    managed_run.runtime.values = {"COMPOSE_PROJECT_NAME": "lotus-e2e-smoke-1234"}
    captured: list[tuple[list[str], Path, dict[str, str] | None]] = []

    def fake_capture(
        cmd: list[str],
        cwd: Path,
        *,
        environment: dict[str, str] | None = None,
    ) -> str:
        captured.append((cmd, cwd, environment))
        return "postgres-container"

    monkeypatch.setattr(docker_endpoint_smoke, "_run_capture", fake_capture)

    assert (
        _resolve_postgres_container(
            repo_root=Path("/repo"),
            compose_file="/repo/docker-compose.yml",
            postgres_service="postgres",
            managed_run=managed_run,
        )
        == "postgres-container"
    )
    assert captured == [
        (
            managed_run.compose_command.return_value,
            Path("/repo"),
            managed_run.runtime.values,
        )
    ]


def test_main_reenters_under_managed_dynamic_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for environment_key in (
        "E2E_INGESTION_URL",
        "E2E_QUERY_URL",
        "E2E_EVENT_REPLAY_URL",
        "E2E_QUERY_CONTROL_PLANE_URL",
    ):
        monkeypatch.delenv(environment_key, raising=False)
    args = SimpleNamespace(
        repo_root=str(tmp_path),
        compose_file="docker-compose.yml",
        ingestion_base_url=None,
        query_base_url=None,
        event_replay_base_url=None,
        query_control_plane_base_url=None,
        skip_compose=False,
        build=False,
        compose_log_path="output/task-runs/diagnostics/docker-smoke.log",
        keep_compose=False,
        reset_volumes=False,
    )
    managed_run = MagicMock()
    managed_run.__enter__.return_value = managed_run
    managed_run.__exit__.return_value = False
    managed_run.runtime.endpoints = SimpleNamespace(
        e2e_ingestion_url="http://localhost:15000",
        e2e_query_url="http://localhost:15001",
        e2e_event_replay_url="http://localhost:15009",
        e2e_query_control_plane_url="http://localhost:15002",
    )
    prepared: list[dict[str, object]] = []
    reentered: list[tuple[object, object]] = []
    original_main = docker_endpoint_smoke.main

    monkeypatch.setattr(
        docker_endpoint_smoke,
        "prepare_managed_compose_run",
        lambda **kwargs: prepared.append(kwargs) or managed_run,
    )
    monkeypatch.setattr(
        docker_endpoint_smoke,
        "main",
        lambda args, managed: reentered.append((args, managed)) or 0,
    )

    assert original_main(args, None) == 0
    assert prepared[0]["scope"] == "docker-smoke"
    assert prepared[0]["services"] == tuple(docker_endpoint_smoke.DOCKER_SMOKE_SERVICES)
    assert args.ingestion_base_url == "http://localhost:15000"
    assert args.query_base_url == "http://localhost:15001"
    assert reentered == [(args, managed_run)]
