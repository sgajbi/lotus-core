from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_app_local_compose_declares_machine_readable_stack_contract() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")

    assert compose["name"] == "lotus-core-app-local"
    contract = compose["x-lotus-stack-contract"]
    assert contract["stack_classification"] == "app-local"
    assert contract["canonical_shared_infra"] is False
    assert contract["canonical_owner"] == "lotus-core"
    assert contract["canonical_shared_infra_owner"] == "lotus-platform/platform-stack"


def test_app_local_compose_contract_declares_local_debug_use_cases() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")

    assert compose["x-lotus-stack-contract"]["purpose"] == [
        "isolated-development",
        "service-local-debugging",
        "app-local-observability",
    ]


def test_app_local_compose_keeps_local_overlay_services_available() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    services = compose["services"]

    for service_name in [
        "zookeeper",
        "kafka",
        "postgres",
        "prometheus",
        "grafana",
        "demo_data_loader",
    ]:
        assert service_name in services


def test_demo_data_loader_uses_internal_service_urls() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    command = compose["services"]["demo_data_loader"]["command"]

    assert "--ingestion-base-url http://ingestion_service:8000" in command
    assert "--query-base-url http://query_service:8001" in command
    assert (
        "--query-control-plane-base-url http://query_control_plane_service:8002"
        in command
    )
