"""Prebuild compose-backed service images with reusable BuildKit cache."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import UTC, datetime
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

PROVENANCE_BUILD_ARGS = (
    "LOTUS_GIT_COMMIT_SHA",
    "LOTUS_GIT_BRANCH",
    "LOTUS_BUILD_TIMESTAMP",
    "LOTUS_REPO_URL",
    "LOTUS_IMAGE_VERSION",
    "LOTUS_IMAGE_DIGEST",
    "LOTUS_CI_RUN_ID",
)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def _command_output(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _resolve_repo_url() -> str:
    explicit_repo_url = os.getenv("LOTUS_REPO_URL", "").strip()
    if explicit_repo_url:
        return explicit_repo_url
    github_repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if github_repository:
        server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        return f"{server_url}/{github_repository}"
    return _command_output(["git", "config", "--get", "remote.origin.url"]) or "unknown"


def _resolve_git_branch() -> str:
    for env_name in ("LOTUS_GIT_BRANCH", "GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return _command_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"


def resolve_build_metadata() -> dict[str, str]:
    return {
        "LOTUS_GIT_COMMIT_SHA": (
            os.getenv("LOTUS_GIT_COMMIT_SHA", "").strip()
            or os.getenv("GITHUB_SHA", "").strip()
            or _command_output(["git", "rev-parse", "HEAD"])
            or "unknown"
        ),
        "LOTUS_GIT_BRANCH": _resolve_git_branch(),
        "LOTUS_BUILD_TIMESTAMP": (
            os.getenv("LOTUS_BUILD_TIMESTAMP", "").strip()
            or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ),
        "LOTUS_REPO_URL": _resolve_repo_url(),
        "LOTUS_IMAGE_VERSION": (
            os.getenv("LOTUS_IMAGE_VERSION", "").strip()
            or os.getenv("GITHUB_REF_NAME", "").strip()
            or os.getenv("GITHUB_SHA", "").strip()
            or _command_output(["git", "rev-parse", "HEAD"])
            or "unknown"
        ),
        "LOTUS_IMAGE_DIGEST": os.getenv("LOTUS_IMAGE_DIGEST", "").strip() or "unknown",
        "LOTUS_CI_RUN_ID": (
            os.getenv("LOTUS_CI_RUN_ID", "").strip()
            or os.getenv("GITHUB_RUN_ID", "").strip()
            or "unknown"
        ),
    }


def provenance_build_args(metadata: dict[str, str] | None = None) -> list[str]:
    resolved_metadata = metadata or resolve_build_metadata()
    build_args: list[str] = []
    for name in PROVENANCE_BUILD_ARGS:
        build_args.extend(["--build-arg", f"{name}={resolved_metadata[name]}"])
    return build_args


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
        *provenance_build_args(),
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
