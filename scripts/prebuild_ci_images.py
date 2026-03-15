"""Prebuild compose-backed service images with reusable BuildKit cache."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
try:
    from scripts.ci_service_sets import PREBUILD_GROUPS
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from ci_service_sets import PREBUILD_GROUPS

SERVICE_BUILDS: dict[str, tuple[str, str]] = {
    "kafka-topic-creator": (
        "lotus-core/kafka-topic-creator:local",
        "src/services/persistence_service/Dockerfile",
    ),
    "migration-runner": (
        "lotus-core/migration-runner:local",
        "src/services/persistence_service/Dockerfile",
    ),
    "ingestion_service": (
        "lotus-core/ingestion-service:local",
        "src/services/ingestion_service/Dockerfile",
    ),
    "query_service": (
        "lotus-core/query-service:local",
        "src/services/query_service/Dockerfile",
    ),
    "query_control_plane_service": (
        "lotus-core/query-control-plane-service:local",
        "src/services/query_control_plane_service/Dockerfile",
    ),
    "event_replay_service": (
        "lotus-core/event-replay-service:local",
        "src/services/event_replay_service/Dockerfile",
    ),
    "financial_reconciliation_service": (
        "lotus-core/financial-reconciliation-service:local",
        "src/services/financial_reconciliation_service/Dockerfile",
    ),
    "persistence_service": (
        "lotus-core/persistence-service:local",
        "src/services/persistence_service/Dockerfile",
    ),
    "cost_calculator_service": (
        "lotus-core/cost-calculator-service:local",
        "src/services/calculators/cost_calculator_service/Dockerfile",
    ),
    "cashflow_calculator_service": (
        "lotus-core/cashflow-calculator-service:local",
        "src/services/calculators/cashflow_calculator_service/Dockerfile",
    ),
    "position_calculator_service": (
        "lotus-core/position-calculator-service:local",
        "src/services/calculators/position_calculator/Dockerfile",
    ),
    "pipeline_orchestrator_service": (
        "lotus-core/pipeline-orchestrator-service:local",
        "src/services/pipeline_orchestrator_service/Dockerfile",
    ),
    "valuation_orchestrator_service": (
        "lotus-core/valuation-orchestrator-service:local",
        "src/services/valuation_orchestrator_service/Dockerfile",
    ),
    "position_valuation_calculator": (
        "lotus-core/position-valuation-calculator:local",
        "src/services/calculators/position_valuation_calculator/Dockerfile",
    ),
    "timeseries_generator_service": (
        "lotus-core/timeseries-generator-service:local",
        "src/services/timeseries_generator_service/Dockerfile",
    ),
    "portfolio_aggregation_service": (
        "lotus-core/portfolio-aggregation-service:local",
        "src/services/portfolio_aggregation_service/Dockerfile",
    ),
    "demo_data_loader": (
        "lotus-core/demo-data-loader:local",
        "src/services/persistence_service/Dockerfile",
    ),
}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def _swap_cache(cache_dir: Path, next_cache_dir: Path) -> None:
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    next_cache_dir.rename(cache_dir)


def _build(service: str, cache_dir: Path) -> None:
    tag, dockerfile = SERVICE_BUILDS[service]
    next_cache_dir = cache_dir.parent / f"{cache_dir.name}-next"
    if next_cache_dir.exists():
        shutil.rmtree(next_cache_dir)

    cmd = [
        "docker",
        "buildx",
        "build",
        "--load",
        "--file",
        dockerfile,
        "--tag",
        tag,
        "--cache-to",
        f"type=local,dest={next_cache_dir},mode=max",
        ".",
    ]
    if cache_dir.exists():
        cmd.extend(["--cache-from", f"type=local,src={cache_dir}"])

    print(f"Prebuilding {service} -> {tag}")
    _run(cmd)
    _swap_cache(cache_dir, next_cache_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        default=".buildx-cache",
        help="Local buildx cache directory reused across CI runs.",
    )
    parser.add_argument(
        "--services",
        nargs="*",
        default=None,
        help="Subset of compose service names to prebuild.",
    )
    parser.add_argument(
        "--group",
        choices=sorted(PREBUILD_GROUPS),
        help="Named CI service subset to prebuild.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    services = list(args.services) if args.services is not None else []
    if args.group:
        for service in PREBUILD_GROUPS[args.group]:
            if service not in services:
                services.append(service)
    if not services:
        services = sorted(SERVICE_BUILDS)

    unknown = sorted(set(services) - set(SERVICE_BUILDS))
    if unknown:
        raise SystemExit(f"Unknown services: {', '.join(unknown)}")

    cache_dir = (REPO_ROOT / args.cache_dir).resolve()
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    for service in services:
        _build(service, cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
