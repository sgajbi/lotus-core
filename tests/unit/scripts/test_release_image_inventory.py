from pathlib import Path

import yaml

from scripts.release.prebuild_ci_images import SERVICE_BUILDS
from scripts.release.render_release_deployment import DEPLOYMENT_TARGETS

REPO_ROOT = Path(__file__).resolve().parents[3]
LEGACY_TRANSACTION_WORKERS = {
    "cost_calculator_service",
    "cashflow_calculator_service",
    "position_calculator_service",
}
TARGET_TRANSACTION_WORKER = "portfolio_transaction_processing_service"
TARGET_DERIVED_STATE_WORKER = "portfolio_derived_state_service"
RETIRED_DERIVED_STATE_WORKERS = {
    "portfolio_aggregation_service",
    "timeseries_generator_service",
}


def test_ci_prebuild_inventory_contains_only_the_unified_transaction_worker() -> None:
    assert TARGET_TRANSACTION_WORKER in SERVICE_BUILDS
    assert not LEGACY_TRANSACTION_WORKERS.intersection(SERVICE_BUILDS)


def test_legacy_transaction_source_roots_are_not_standalone_packages_or_images() -> None:
    source_roots = (
        REPO_ROOT / "src/services/calculators/cost_calculator_service",
        REPO_ROOT / "src/services/calculators/cashflow_calculator_service",
        REPO_ROOT / "src/services/calculators/position_calculator",
    )

    for source_root in source_roots:
        assert not (source_root / "Dockerfile").exists()
        assert not (source_root / "pyproject.toml").exists()
        assert not (source_root / "requirements.txt").exists()


def test_dependabot_tracks_only_unified_runtime_packages_and_images() -> None:
    config = yaml.safe_load((REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    transaction_directories = {
        "/src/services/calculators/cashflow_calculator_service",
        "/src/services/calculators/cost_calculator_service",
        "/src/services/calculators/position_calculator",
    }
    for update in config["updates"]:
        directories = set(update.get("directories", []))
        assert not transaction_directories.intersection(directories)

    target = "/src/services/portfolio_transaction_processing_service"
    pip_directories = next(
        update["directories"]
        for update in config["updates"]
        if update["package-ecosystem"] == "pip"
    )
    docker_directories = next(
        update["directories"]
        for update in config["updates"]
        if update["package-ecosystem"] == "docker"
    )
    assert target in pip_directories
    assert target in docker_directories
    derived_state_target = "/src/services/portfolio_derived_state_service"
    assert derived_state_target in pip_directories
    assert derived_state_target in docker_directories
    assert {
        "/src/services/portfolio_aggregation_service",
        "/src/services/timeseries_generator_service",
    }.isdisjoint(set(pip_directories) | set(docker_directories))


def test_image_release_contains_only_unified_release_managed_workers() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "image-release.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    matrix = workflow["jobs"]["publish-images"]["strategy"]["matrix"]["include"]
    services = {entry["service"] for entry in matrix}
    target = next(entry for entry in matrix if entry["service"] == TARGET_TRANSACTION_WORKER)
    derived_state_target = next(
        entry for entry in matrix if entry["service"] == TARGET_DERIVED_STATE_WORKER
    )

    assert not LEGACY_TRANSACTION_WORKERS.intersection(services)
    assert not RETIRED_DERIVED_STATE_WORKERS.intersection(services)
    assert target == {
        "service": TARGET_TRANSACTION_WORKER,
        "image_name": "portfolio-transaction-processing-service",
        "dockerfile": "src/services/portfolio_transaction_processing_service/Dockerfile",
    }
    assert derived_state_target == {
        "service": TARGET_DERIVED_STATE_WORKER,
        "image_name": "portfolio-derived-state-service",
        "dockerfile": "src/services/portfolio_derived_state_service/Dockerfile",
    }
    assert set(DEPLOYMENT_TARGETS) == {
        TARGET_TRANSACTION_WORKER,
        TARGET_DERIVED_STATE_WORKER,
    }
    assert "render_release_deployment.py" in workflow_text
    assert "portfolio_transaction_processing_service-kubernetes.yaml" not in workflow_text
    assert "${{ matrix.service }}-kubernetes.yaml" in workflow_text
