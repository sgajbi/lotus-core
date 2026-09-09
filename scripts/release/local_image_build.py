"""Run supported local image builds with source-derived provenance."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess  # nosec B404 - fixed executable arguments, never a shell
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/sgajbi/lotus-core"
LOCAL_IMAGE_DIGEST = "unavailable-before-push"
LOCAL_CI_RUN_ID = "unavailable-local-build"
LOCAL_COMPOSE_FILE = "docker-compose.yml"

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


def _has_hidden_index_flags(root: Path, *, runner: Runner) -> bool:
    entries = _git(root, "ls-files", "-v", "-z", runner=runner).split("\0")
    return any(entry and (entry[0].islower() or entry[0] == "S") for entry in entries)


def _dockerignore_patterns(root: Path) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _is_docker_ignored(path: Path, *, root: Path, patterns: Sequence[str]) -> bool:
    relative = path.relative_to(root).as_posix()
    candidate = PurePosixPath(relative)
    ignored = False
    for raw_pattern in patterns:
        negated = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if negated else raw_pattern
        pattern = pattern.strip("/")
        if not pattern:
            continue
        matched = candidate.match(pattern)
        if "/" not in pattern:
            matched = matched or pattern in candidate.parts
        if matched:
            ignored = not negated
    return ignored


def _copied_source_directories(root: Path) -> set[Path]:
    directories: set[Path] = set()
    for dockerfile in (root / "src" / "services").rglob("Dockerfile"):
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().upper().startswith("COPY "):
                continue
            tokens = shlex.split(line, posix=True)
            arguments = [token for token in tokens[1:] if not token.startswith("--")]
            for source in arguments[:-1]:
                candidate = (root / source).resolve()
                if candidate.is_dir() and candidate.is_relative_to(root.resolve()):
                    directories.add(candidate)
    return directories


def _has_untracked_empty_context_directory(root: Path) -> bool:
    patterns = _dockerignore_patterns(root)
    return any(
        directory.is_dir()
        and not any(directory.iterdir())
        and not _is_docker_ignored(directory, root=root, patterns=patterns)
        for source_root in _copied_source_directories(root)
        for directory in source_root.rglob("*")
    )


def _is_within_copied_source(path: Path, *, copied_sources: set[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(source) for source in copied_sources)


def discover_local_build_metadata(
    root: Path = REPO_ROOT,
    *,
    runner: Runner = subprocess.run,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> LocalBuildMetadata:
    commit = _git(root, "rev-parse", "--verify", "HEAD", runner=runner)
    branch = _git(root, "branch", "--show-current", runner=runner) or "detached-head"
    # The build context observes executable-bit changes even when a developer's
    # local Git configuration asks status to ignore them.
    dirty = bool(
        _git(
            root,
            "-c",
            "core.fileMode=true",
            "status",
            "--porcelain",
            "--untracked-files=all",
            runner=runner,
        )
    )
    if not dirty:
        # Git hides assume-unchanged and skip-worktree paths from ordinary
        # status even though Docker still reads their working-tree content.
        dirty = _has_hidden_index_flags(root, runner=runner)
    if not dirty:
        git_ignored = set(
            _git(
                root,
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                runner=runner,
            ).splitlines()
        )
        docker_ignored = set(
            _git(
                root,
                "ls-files",
                "--others",
                "--ignored",
                f"--exclude-from={root / '.dockerignore'}",
                runner=runner,
            ).splitlines()
        )
        copied_sources = _copied_source_directories(root)
        dirty = any(
            _is_within_copied_source(root / relative, copied_sources=copied_sources)
            for relative in git_ignored - docker_ignored
        )
    if not dirty:
        dirty = _has_untracked_empty_context_directory(root)
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
    command = [
        "docker",
        "compose",
        "-f",
        LOCAL_COMPOSE_FILE,
        "up",
        "--detach",
        "--build",
    ]
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
