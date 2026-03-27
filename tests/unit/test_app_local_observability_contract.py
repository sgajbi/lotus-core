from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_app_local_prometheus_scrapes_the_expected_lotus_core_services() -> None:
    prometheus = _read_yaml(ROOT / "prometheus" / "prometheus.yml")
    actual_jobs = {job["job_name"] for job in prometheus["scrape_configs"]}

    assert actual_jobs == {
        "ingestion_service",
        "query_service",
        "query_control_plane_service",
        "event_replay_service",
        "financial_reconciliation_service",
        "persistence_service",
        "position_calculator_service",
        "pipeline_orchestrator_service",
        "valuation_orchestrator_service",
        "cashflow_calculator_service",
        "cost_calculator_service",
        "position_valuation_calculator",
        "timeseries_generator_service",
        "portfolio_aggregation_service",
    }


def test_app_local_prometheus_targets_match_local_compose_service_names() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    prometheus = _read_yaml(ROOT / "prometheus" / "prometheus.yml")

    services = compose["services"]
    for job in prometheus["scrape_configs"]:
        target = job["static_configs"][0]["targets"][0]
        host = target.split(":", maxsplit=1)[0]
        assert host in services
