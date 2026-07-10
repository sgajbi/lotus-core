from __future__ import annotations

import json
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


def test_app_local_grafana_overlay_files_are_explicitly_marked_non_canonical() -> None:
    datasource = (ROOT / "grafana" / "provisioning" / "datasources" / "datasource.yml").read_text(
        encoding="utf-8"
    )
    dashboards = (ROOT / "grafana" / "provisioning" / "dashboards" / "dashboard.yml").read_text(
        encoding="utf-8"
    )

    assert "App-local" in datasource
    assert "lotus-platform/platform-stack" in datasource
    assert "App-local" in dashboards
    assert "lotus-platform/platform-stack" in dashboards


def test_transaction_processing_dashboard_covers_cutover_signals() -> None:
    dashboard = json.loads(
        (ROOT / "grafana" / "dashboards" / "transaction_processing.json").read_text(
            encoding="utf-8"
        )
    )
    panels = dashboard["panels"]
    panel_titles = {panel["title"] for panel in panels}
    expressions = "\n".join(
        target["expr"] for panel in panels for target in panel.get("targets", [])
    )

    assert dashboard["uid"] == "lotus-core-transaction-processing"
    assert panel_titles == {
        "Live Consumer Lag",
        "Replay Consumer Lag",
        "Stage p95 Duration",
        "Processing Failure Rate",
        "Async DB Pool State",
        "Outbox Backlog",
    }
    assert "portfolio_transaction_processing_group" in expressions
    assert "portfolio_transaction_replay_request_group" in expressions
    assert "kafka_consumer_partition_lag_messages" in expressions
    assert "lotus_core_transaction_processing_operation_duration_seconds_bucket" in expressions
    assert "lotus_core_transaction_processing_operations_total" in expressions
    assert "database_pool_connections" in expressions
    assert "outbox_events_pending" in expressions
    assert "outbox_events_oldest_pending_age_seconds" in expressions
    assert not {
        "portfolio_id",
        "transaction_id",
        "correlation_id",
        "trace_id",
    }.intersection(expressions)
