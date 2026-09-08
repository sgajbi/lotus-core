"""Run supported local image builds with source-derived provenance."""

from __future__ import annotations

import argparse
import os
import subprocess  # nosec B404 - fixed executable arguments, never a shell
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/sgajbi/lotus-core"
LOCAL_IMAGE_DIGEST = "unavailable-before-push"
LOCAL_CI_RUN_ID = "unavailable-local-build"

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class LocalBuildMetadata:
    git_commit_sha: str
    git_branch: str
    build_timestamp: str
    repo_url: str
    image_version: str
    image_digest: str = LOCAL_IMAGE_DIGEST
    ci_run_id: str = LOCAL_CI_RUN_ID

    def environment(self) -> dict[str, str]:
        return {
            "LOTUS_GIT_COMMIT_SHA": self.git_commit_sha,
            "LOTUS_GIT_BRANCH": self.git_branch,
            "LOTUS_BUILD_TIMESTAMP": self.build_timestamp,
            "LOTUS_REPO_URL": self.repo_url,
            "LOTUS_IMAGE_VERSION": self.image_version,
            "LOTUS_IMAGE_DIGEST": self.image_digest,
            "LOTUS_CI_RUN_ID": self.ci_run_id,
        }


def _git(root: Path, *arguments: str, runner: Runner) -> str:
    result = runner(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def discover_local_build_metadata(
    root: Path = REPO_ROOT,
    *,
    runner: Runner = subprocess.run,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> LocalBuildMetadata:
    commit = _git(root, "rev-parse", "--verify", "HEAD", runner=runner)
    branch = _git(root, "branch", "--show-current", runner=runner) or "detached-head"
    dirty = bool(_git(root, "status", "--porcelain", runner=runner))
    with (root / "pyproject.toml").open("rb") as handle:
        project_version = str(tomllib.load(handle)["project"]["version"])
    return LocalBuildMetadata(
        git_commit_sha=f"{commit}-dirty" if dirty else commit,
        git_branch=branch,
        build_timestamp=now().astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        repo_url=REPO_URL,
        image_version=f"{project_version}-local.{commit[:12]}",
    )


def docker_build_command(metadata: LocalBuildMetadata) -> list[str]:
    command = [
        "docker",
        "build",
        "-f",
        "src/services/query_service/Dockerfile",
        "-t",
        "portfolio-analytics-query-service:ci",
    ]
    for name, value in metadata.environment().items():
        command.extend(("--build-arg", f"{name}={value}"))
    return [*command, "."]


def compose_up_command(services: Sequence[str], *, no_deps: bool) -> list[str]:
    command = ["docker", "compose", "up", "--detach", "--build"]
    if no_deps:
        command.append("--no-deps")
    return [*command, *services]


def run_local_build(
    command: Sequence[str],
    metadata: LocalBuildMetadata,
    *,
    runner: Runner = subprocess.run,
) -> None:
    environment = os.environ.copy()
    environment.update(metadata.environment())
    runner(list(command), check=True, cwd=REPO_ROOT, env=environment)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("docker-build", help="Build the local query-service image.")
    compose = subparsers.add_parser(
        "compose-up", help="Build and start the app-local Compose stack."
    )
    compose.add_argument("--no-deps", action="store_true")
    compose.add_argument("services", nargs="*")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    metadata = discover_local_build_metadata()
    if args.operation == "docker-build":
        command = docker_build_command(metadata)
    else:
        command = compose_up_command(args.services, no_deps=args.no_deps)
    run_local_build(command, metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
