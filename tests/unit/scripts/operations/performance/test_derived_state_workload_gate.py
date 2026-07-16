"""Tests for managed derived-state workload profile orchestration."""

from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.operations.performance.derived_state_workload_gate import (
    build_bank_day_command,
    build_workload_environment,
    prepare_managed_run,
    resolve_workload_profile,
    resolve_workload_trade_date,
    validate_execution_posture,
)
from scripts.quality.ci_service_sets import DERIVED_STATE_WORKLOAD_GATE_SERVICES

ROOT = Path(__file__).resolve().parents[5]


def test_daily_profile_models_the_governed_bank_day_volume() -> None:
    profile = resolve_workload_profile(profile_name="daily", diagnostic_smoke=False)

    assert profile.name == "derived-state-daily-volume"
    assert profile.portfolio_count == 1000
    assert profile.positions_per_portfolio == 100
    assert profile.transaction_count == 100_000
    assert profile.seed_materialization_timeout_seconds == 600
    assert profile.certifying is True


def test_fan_in_profile_concentrates_positions_in_one_portfolio() -> None:
    profile = resolve_workload_profile(profile_name="fan-in", diagnostic_smoke=False)

    assert profile.name == "derived-state-aggregation-fan-in"
    assert profile.portfolio_count == 1
    assert profile.positions_per_portfolio == 1000
    assert profile.transaction_count == 1000
    assert profile.certifying is True


def test_price_burst_profile_revalues_shared_instruments_across_portfolios() -> None:
    profile = resolve_workload_profile(profile_name="price-burst", diagnostic_smoke=False)

    assert profile.name == "derived-state-market-price-correction-burst"
    assert profile.portfolio_count == 100
    assert profile.positions_per_portfolio == 100
    assert profile.transaction_count == 10_000
    assert profile.market_price_correction_multiplier == Decimal("1.05")
    assert profile.certifying is True


def test_price_restatement_profile_rebuilds_a_bounded_business_date_window() -> None:
    profile = resolve_workload_profile(profile_name="price-restatement", diagnostic_smoke=False)

    assert profile.name == "derived-state-market-price-restatement"
    assert profile.transaction_count == 10_000
    assert profile.business_date_count == 5
    assert profile.market_price_correction_multiplier == Decimal("1.05")
    assert profile.certifying is True


def test_fx_restatement_profile_rebuilds_only_the_affected_direct_pair() -> None:
    profile = resolve_workload_profile(profile_name="fx-restatement", diagnostic_smoke=False)

    assert profile.name == "derived-state-fx-rate-restatement"
    assert profile.transaction_count == 10_000
    assert profile.business_date_count == 5
    assert profile.fx_rate_correction_from_currency == "EUR"
    assert profile.fx_rate_correction_to_currency == "USD"
    assert profile.fx_rate_correction_multiplier == Decimal("1.05")
    assert profile.restart_valuation_orchestrator_during_fx_correction is True
    assert profile.certifying is True


def test_diagnostic_smoke_profile_cannot_be_mistaken_for_capacity_proof() -> None:
    profile = resolve_workload_profile(profile_name="daily", diagnostic_smoke=True)

    assert profile.name == "diagnostic-derived-state-workload-smoke"
    assert profile.transaction_count == 10
    assert profile.certifying is False


def test_workload_trade_date_is_explicit_for_an_empty_managed_database() -> None:
    now = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)

    assert resolve_workload_trade_date(explicit_trade_date=None, now=now) == "2026-07-15"
    assert resolve_workload_trade_date(explicit_trade_date="2026-04-10", now=now) == "2026-04-10"


def test_implicit_workload_trade_date_rolls_weekend_back_to_friday() -> None:
    sunday = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)

    assert resolve_workload_trade_date(explicit_trade_date=None, now=sunday) == "2026-07-17"


def test_explicit_workload_trade_date_rejects_weekends() -> None:
    with pytest.raises(ValueError, match="explicit trade date must be a weekday"):
        resolve_workload_trade_date(
            explicit_trade_date="2026-07-19",
            now=datetime(2026, 7, 15, tzinfo=UTC),
        )


def test_bank_day_command_uses_managed_endpoints_and_exact_profile_shape(tmp_path: Path) -> None:
    profile = resolve_workload_profile(profile_name="fan-in", diagnostic_smoke=False)
    endpoints = SimpleNamespace(
        compose_project_name="derived-state-fan-in-proof",
        host_database_url="postgresql://user:password@localhost:55001/core",
        e2e_ingestion_url="http://localhost:55002",
        e2e_query_url="http://localhost:55003",
        e2e_query_control_plane_url="http://localhost:55004",
        e2e_event_replay_url="http://localhost:55005",
        e2e_financial_reconciliation_url="http://localhost:55006",
    )
    command = build_bank_day_command(
        python_executable="python",
        repo_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        endpoints=endpoints,
        profile=profile,
        output_dir="output/task-runs",
        resource_poll_interval_seconds=2.5,
        trade_date="2026-07-15",
    )

    assert command[:4] == [
        "python",
        "-m",
        "scripts.operations.bank_day_load_scenario",
        "--compose-file",
    ]
    assert "derived-state-aggregation-fan-in" in command
    assert command[command.index("--evidence-classification") + 1] == "certifying"
    assert command[command.index("--portfolio-count") + 1] == "1"
    assert command[command.index("--transactions-per-portfolio") + 1] == "1000"
    assert command[command.index("--transaction-batch-size") + 1] == "1000"
    assert command[command.index("--compose-project-name") + 1] == ("derived-state-fan-in-proof")
    assert "--host-database-url" not in command
    assert endpoints.host_database_url not in command
    assert command[command.index("--trade-date") + 1] == "2026-07-15"
    assert command[command.index("--business-date-count") + 1] == "1"
    assert command[command.index("--seed-materialization-timeout-seconds") + 1] == "600"
    assert "--derived-state-service" in command
    assert "--market-price-correction-multiplier" not in command

    environment = build_workload_environment(
        endpoints=endpoints,
        base_environment={"PATH": "C:/tools"},
    )
    assert environment["HOST_DATABASE_URL"] == endpoints.host_database_url
    assert environment["PATH"] == "C:/tools"


def test_price_burst_command_requests_a_measured_market_price_correction(tmp_path: Path) -> None:
    profile = resolve_workload_profile(profile_name="price-burst", diagnostic_smoke=False)
    endpoints = SimpleNamespace(
        compose_project_name="derived-state-price-burst-proof",
        host_database_url="postgresql://user:password@localhost:55001/core",
        e2e_ingestion_url="http://localhost:55002",
        e2e_query_url="http://localhost:55003",
        e2e_query_control_plane_url="http://localhost:55004",
        e2e_event_replay_url="http://localhost:55005",
        e2e_financial_reconciliation_url="http://localhost:55006",
    )

    command = build_bank_day_command(
        python_executable="python",
        repo_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        endpoints=endpoints,
        profile=profile,
        output_dir="output/task-runs",
        resource_poll_interval_seconds=5.0,
        trade_date="2026-07-15",
    )

    assert command[command.index("--market-price-correction-multiplier") + 1] == "1.05"


def test_price_restatement_command_requests_a_five_day_correction_window(
    tmp_path: Path,
) -> None:
    profile = resolve_workload_profile(profile_name="price-restatement", diagnostic_smoke=False)
    endpoints = SimpleNamespace(
        compose_project_name="derived-state-price-restatement-proof",
        host_database_url="postgresql://user:password@localhost:55001/core",
        e2e_ingestion_url="http://localhost:55002",
        e2e_query_url="http://localhost:55003",
        e2e_query_control_plane_url="http://localhost:55004",
        e2e_event_replay_url="http://localhost:55005",
        e2e_financial_reconciliation_url="http://localhost:55006",
    )

    command = build_bank_day_command(
        python_executable="python",
        repo_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        endpoints=endpoints,
        profile=profile,
        output_dir="output/task-runs",
        resource_poll_interval_seconds=5.0,
        trade_date="2026-07-15",
    )

    assert command[command.index("--business-date-count") + 1] == "5"
    assert command[command.index("--market-price-correction-multiplier") + 1] == "1.05"


def test_fx_restatement_command_requests_a_five_day_direct_pair_correction(
    tmp_path: Path,
) -> None:
    profile = resolve_workload_profile(profile_name="fx-restatement", diagnostic_smoke=False)
    endpoints = SimpleNamespace(
        compose_project_name="derived-state-fx-restatement-proof",
        host_database_url="postgresql://user:password@localhost:55001/core",
        e2e_ingestion_url="http://localhost:55002",
        e2e_query_url="http://localhost:55003",
        e2e_query_control_plane_url="http://localhost:55004",
        e2e_event_replay_url="http://localhost:55005",
        e2e_financial_reconciliation_url="http://localhost:55006",
    )

    command = build_bank_day_command(
        python_executable="python",
        repo_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        endpoints=endpoints,
        profile=profile,
        output_dir="output/task-runs",
        resource_poll_interval_seconds=5.0,
        trade_date="2026-07-15",
    )

    assert command[command.index("--business-date-count") + 1] == "5"
    assert command[command.index("--fx-rate-correction-from-currency") + 1] == "EUR"
    assert command[command.index("--fx-rate-correction-to-currency") + 1] == "USD"
    assert command[command.index("--fx-rate-correction-multiplier") + 1] == "1.05"
    assert "--restart-valuation-orchestrator-during-fx-correction" in command


def test_certifying_profile_requires_exact_source_build() -> None:
    certifying = resolve_workload_profile(profile_name="fan-in", diagnostic_smoke=False)
    diagnostic = resolve_workload_profile(profile_name="daily", diagnostic_smoke=True)

    validate_execution_posture(profile=certifying, build=True)
    validate_execution_posture(profile=diagnostic, build=False)

    with pytest.raises(
        ValueError,
        match="Certifying derived-state workload profiles require --build",
    ):
        validate_execution_posture(profile=certifying, build=False)


def test_prepare_managed_run_uses_complete_derived_state_service_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    def fake_prepare(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.prepare_managed_compose_run",
        fake_prepare,
    )
    args = Namespace(
        compose_file="docker-compose.yml",
        compose_project_name=None,
        skip_compose=False,
        build=False,
        keep_stack_up=False,
        output_dir="output/task-runs",
        profile="daily",
        ingestion_base_url=None,
        query_base_url=None,
        query_control_base_url=None,
        event_replay_base_url=None,
        reconciliation_base_url=None,
        host_database_url=None,
    )

    result = prepare_managed_run(args=args, repo_root=tmp_path)

    assert result is expected
    assert captured["scope"] == "derived-state-daily-workload"
    assert captured["services"] == DERIVED_STATE_WORKLOAD_GATE_SERVICES
    assert captured["allocate_dynamic_ports"] is True
    assert captured["enable_demo_data_pack"] is False


def test_make_targets_keep_diagnostic_and_certifying_profiles_explicit() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "test-derived-state-workload-smoke:" in makefile
    assert "--diagnostic-smoke" in makefile
    assert "profile-derived-state-daily:" in makefile
    assert "--profile daily" in makefile
    assert "profile-derived-state-fan-in:" in makefile
    assert "--profile fan-in" in makefile
    assert "profile-derived-state-price-burst:" in makefile
    assert "--profile price-burst" in makefile
    assert "profile-derived-state-price-restatement:" in makefile
    assert "--profile price-restatement" in makefile
    assert "profile-derived-state-fx-restatement:" in makefile
    assert "--profile fx-restatement" in makefile
