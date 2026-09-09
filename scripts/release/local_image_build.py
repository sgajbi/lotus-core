"""Run supported local image builds with source-derived provenance."""

from __future__ import annotations

import argparse
import json
import os
import re
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
    if any((root / "src" / "services").rglob("Dockerfile.dockerignore")):
        raise ValueError("Dockerfile-specific ignore files are not supported")
    patterns: list[str] = []
    for line in (root / ".dockerignore").read_text(encoding="utf-8").splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        if pattern.startswith("!"):
            raise ValueError("negated Dockerignore patterns are not supported")
        patterns.append(pattern)
    return tuple(patterns)


def _dockerfile_logical_lines(content: str) -> tuple[str, ...]:
    for physical_line in content.splitlines():
        directive = re.match(r"^\s*#\s*escape\s*=\s*(\S+)", physical_line, re.IGNORECASE)
        if directive and directive.group(1) != "\\":
            raise ValueError("non-default Dockerfile escape directives are not supported")
    lines: list[str] = []
    current = ""
    for physical_line in content.splitlines():
        fragment = physical_line.strip()
        if (
            not current
            and not fragment.startswith("#")
            and re.search(r"(?:^|\s)<<-?['\"]?[A-Za-z0-9_]", fragment)
        ):
            raise ValueError("Dockerfile heredoc instructions are not supported")
        current = f"{current} {fragment}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        if current:
            lines.append(current)
        current = ""
    if current:
        lines.append(current)
    return tuple(lines)


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
        if pattern.startswith("**/"):
            matched = matched or candidate.match(pattern.removeprefix("**/"))
        if "/" not in pattern:
            matched = matched or pattern in candidate.parts
        if matched:
            ignored = not negated
    return ignored


def _copied_source_paths(root: Path) -> set[Path]:
    paths: set[Path] = set()
    lexical_root = Path(os.path.abspath(root))
    for dockerfile in (root / "src" / "services").rglob("Dockerfile"):
        lines = _dockerfile_logical_lines(dockerfile.read_text(encoding="utf-8"))
        stage_names: set[str] = set()
        current_stage_index = -1
        for line in lines:
            tokens = line.lstrip().split()
            instruction = tokens[0].upper()
            if instruction == "FROM":
                current_stage_index += 1
                if len(tokens) >= 3 and tokens[-2].upper() == "AS":
                    stage_names.add(tokens[-1])
                continue
            if instruction == "ADD":
                raise ValueError("Dockerfile ADD instructions are not supported")
            if instruction == "RUN":
                for token in shlex.split(line)[1:]:
                    if not token.startswith("--mount="):
                        continue
                    mount_options = dict(
                        option.partition("=")[::2]
                        for option in token.removeprefix("--mount=").split(",")
                    )
                    mount_from = mount_options.get("from")
                    numeric_local_stage = (
                        mount_from is not None
                        and mount_from.isdigit()
                        and int(mount_from) < current_stage_index
                    )
                    local_stage = mount_from in stage_names or numeric_local_stage
                    if mount_options.get("type", "bind") == "bind" and not local_stage:
                        raise ValueError("Dockerfile context bind mounts are not supported")
                continue
            if instruction != "COPY":
                continue
            raw_arguments = line.split(maxsplit=1)[1].lstrip()
            copy_from: str | None = None
            while raw_arguments.startswith("--"):
                flag, separator, raw_arguments = raw_arguments.partition(" ")
                if not separator or "=" not in flag:
                    raise ValueError(f"unsupported Dockerfile COPY flag syntax: {line}")
                flag_name, _, flag_value = flag.partition("=")
                if flag_name == "--from":
                    copy_from = flag_value
                raw_arguments = raw_arguments.lstrip()
            if copy_from is not None:
                numeric_local_stage = copy_from.isdigit() and int(copy_from) < current_stage_index
                if copy_from not in stage_names and not numeric_local_stage:
                    raise ValueError(f"Dockerfile external COPY sources are not supported: {line}")
                continue
            if raw_arguments.startswith("["):
                parsed = json.loads(raw_arguments)
                if not isinstance(parsed, list) or not all(
                    isinstance(value, str) for value in parsed
                ):
                    raise ValueError(f"invalid Dockerfile JSON COPY instruction: {line}")
                arguments = parsed
            else:
                arguments = shlex.split(raw_arguments, posix=True)
            if len(arguments) < 2:
                raise ValueError(f"Dockerfile COPY instruction lacks a destination: {line}")
            for source in arguments[:-1]:
                source_path = PurePosixPath(source.replace("\\", "/"))
                if source.startswith(("/", "\\")) or ".." in source_path.parts:
                    raise ValueError(
                        f"Dockerfile absolute or parent COPY sources are not supported: {line}"
                    )
                if "$" in source or any(character in source for character in "*?["):
                    raise ValueError(
                        f"Dockerfile dynamic or wildcard COPY sources are not supported: {line}"
                    )
                candidate = Path(os.path.abspath(root / source))
                if candidate.exists() and candidate.is_relative_to(lexical_root):
                    paths.add(candidate)
    return {
        path
        for path in paths
        if not any(path != other and path.is_relative_to(other) for other in paths)
    }


def _has_untracked_empty_context_directory(
    root: Path,
    *,
    runner: Runner,
) -> bool:
    patterns = _dockerignore_patterns(root)
    copied_sources = _copied_source_paths(root)
    copied_pathspecs = tuple(
        source.relative_to(root).as_posix() for source in sorted(copied_sources)
    )
    tracked_paths = {
        Path(path)
        for path in _git(
            root,
            "ls-files",
            "-z",
            "--",
            *copied_pathspecs,
            runner=runner,
        ).split("\0")
        if path
    }
    for source_root in copied_sources:
        if source_root.is_symlink() or not source_root.is_dir():
            continue
        for current, directory_names, file_names in os.walk(source_root, topdown=True):
            directory = Path(current)
            if _is_docker_ignored(directory, root=root, patterns=patterns):
                directory_names.clear()
                continue
            directory_names[:] = [
                name
                for name in directory_names
                if not _is_docker_ignored(directory / name, root=root, patterns=patterns)
            ]
            visible_files = any(
                not _is_docker_ignored(directory / name, root=root, patterns=patterns)
                for name in file_names
            )
            if not directory_names and not visible_files:
                repository_relative = directory.relative_to(root)
                if not any(path.is_relative_to(repository_relative) for path in tracked_paths):
                    return True
    return False


def _is_within_copied_source(path: Path, *, root: Path, copied_sources: set[Path]) -> bool:
    lexical_root = Path(os.path.abspath(root))
    repository_relative = Path(os.path.abspath(path)).relative_to(lexical_root)
    return any(
        repository_relative.is_relative_to(source.relative_to(lexical_root))
        for source in copied_sources
    )


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
        copied_sources = _copied_source_paths(root)
        copied_pathspecs = tuple(
            source.relative_to(root).as_posix() for source in sorted(copied_sources)
        )
        if copied_pathspecs:
            git_ignored = {
                relative
                for relative in _git(
                    root,
                    "ls-files",
                    "--others",
                    "--ignored",
                    "--exclude-standard",
                    "-z",
                    "--",
                    *copied_pathspecs,
                    runner=runner,
                ).split("\0")
                if relative
            }
            docker_ignored = {
                relative
                for relative in _git(
                    root,
                    "ls-files",
                    "--others",
                    "--ignored",
                    f"--exclude-from={root / '.dockerignore'}",
                    "-z",
                    "--",
                    *copied_pathspecs,
                    runner=runner,
                ).split("\0")
                if relative
            }
            dirty = any(
                _is_within_copied_source(root / relative, root=root, copied_sources=copied_sources)
                for relative in git_ignored - docker_ignored
            )
    if not dirty:
        dirty = _has_untracked_empty_context_directory(root, runner=runner)
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
