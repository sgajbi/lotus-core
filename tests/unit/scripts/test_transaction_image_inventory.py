from pathlib import Path

import yaml

from scripts.prebuild_ci_images import SERVICE_BUILDS

REPO_ROOT = Path(__file__).resolve().parents[3]
LEGACY_TRANSACTION_WORKERS = {
    "cost_calculator_service",
    "cashflow_calculator_service",
    "position_calculator_service",
}
TARGET_TRANSACTION_WORKER = "portfolio_transaction_processing_service"


def test_ci_prebuild_inventory_contains_only_the_unified_transaction_worker() -> None:
    assert TARGET_TRANSACTION_WORKER in SERVICE_BUILDS
    assert not LEGACY_TRANSACTION_WORKERS.intersection(SERVICE_BUILDS)


def test_image_release_contains_only_the_unified_transaction_worker() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "image-release.yml").read_text(
            encoding="utf-8"
        )
    )
    matrix = workflow["jobs"]["publish-images"]["strategy"]["matrix"]["include"]
    services = {entry["service"] for entry in matrix}
    target = next(
        entry for entry in matrix if entry["service"] == TARGET_TRANSACTION_WORKER
    )

    assert not LEGACY_TRANSACTION_WORKERS.intersection(services)
    assert target == {
        "service": TARGET_TRANSACTION_WORKER,
        "image_name": "portfolio-transaction-processing-service",
        "dockerfile": "src/services/portfolio_transaction_processing_service/Dockerfile",
    }
