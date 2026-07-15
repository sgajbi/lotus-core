"""Regression guard for the retired pipeline orchestrator runtime."""

from pathlib import Path

RETIRED_SERVICE_ID = "pipeline_orchestrator_service"
RETIRED_IMAGE_NAME = "pipeline-orchestrator-service"
RETIRED_SERVICE_ROOT = Path("src/services/pipeline_orchestrator_service")
ACTIVE_RUNTIME_INVENTORIES = (
    Path("docker-compose.yml"),
    Path("pyproject.toml"),
    Path("prometheus/prometheus.yml"),
    Path("grafana/dashboards/portfolio_analytics.json"),
    Path(".github/dependabot.yml"),
    Path(".github/workflows/image-release.yml"),
    Path("contracts/security/security-control-coverage.v1.json"),
    Path("scripts/operations/bank_day_load_scenario.py"),
    Path("scripts/quality/ci_service_sets.py"),
    Path("scripts/quality/openapi_quality_gate.py"),
    Path("scripts/release/prebuild_ci_images.py"),
    Path("src/libs/portfolio-common/portfolio_common/event_supportability.py"),
)


def test_pipeline_orchestrator_runtime_does_not_return() -> None:
    assert not RETIRED_SERVICE_ROOT.exists()


def test_active_runtime_inventories_do_not_restore_pipeline_orchestrator() -> None:
    for inventory_path in ACTIVE_RUNTIME_INVENTORIES:
        inventory = inventory_path.read_text(encoding="utf-8")
        assert RETIRED_SERVICE_ID not in inventory, inventory_path
        assert RETIRED_IMAGE_NAME not in inventory, inventory_path
