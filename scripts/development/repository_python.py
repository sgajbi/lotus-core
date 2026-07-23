"""Run Python commands with first-party imports fenced to this repository checkout."""

from __future__ import annotations

import importlib.machinery
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRST_PARTY_PACKAGE = "portfolio_common"
STARTUP_GUARD_ROOT = Path(__file__).resolve().parent / "python_startup"


class RepositoryPythonError(RuntimeError):
    """Raised when a repository command cannot prove current-checkout source ownership."""


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def repository_python_roots(repo_root: Path = ROOT) -> tuple[Path, ...]:
    """Return ordered roots required by repo-native Python entry points."""

    resolved_root = repo_root.resolve()
    return (
        STARTUP_GUARD_ROOT,
        resolved_root / "src" / "libs" / "portfolio-common",
        resolved_root,
    )


def _is_foreign_lotus_core_path(path: Path, *, repo_root: Path) -> bool:
    resolved = path.resolve()
    if _is_within(resolved, repo_root.resolve()):
        return False
    return any(part.casefold().startswith("lotus-core") for part in resolved.parts)


def build_repository_pythonpath(
    *,
    repo_root: Path = ROOT,
    inherited_pythonpath: str = "",
) -> str:
    """Prepend current roots and discard inherited paths from other Core worktrees."""

    roots = repository_python_roots(repo_root)
    entries = [str(root) for root in roots]
    seen = {os.path.normcase(str(root.resolve())) for root in roots}
    for raw_entry in inherited_pythonpath.split(os.pathsep):
        if not raw_entry.strip():
            continue
        entry = Path(raw_entry).resolve()
        normalized = os.path.normcase(str(entry))
        if normalized in seen or _is_foreign_lotus_core_path(entry, repo_root=repo_root):
            continue
        entries.append(str(entry))
        seen.add(normalized)
    return os.pathsep.join(entries)


def require_current_first_party_origin(
    *,
    repo_root: Path = ROOT,
    pythonpath: str,
    package_name: str = FIRST_PARTY_PACKAGE,
) -> Path:
    """Fail unless the fenced search path resolves first-party code in this checkout."""

    search_paths = [entry for entry in pythonpath.split(os.pathsep) if entry]
    spec = importlib.machinery.PathFinder.find_spec(package_name, search_paths)
    origin = None if spec is None else spec.origin
    if not origin:
        raise RepositoryPythonError(
            f"repository source provenance failed: cannot resolve {package_name!r} from "
            f"current checkout {repo_root.resolve()}. Run `make install` and retry."
        )
    resolved_origin = Path(origin).resolve()
    resolved_root = repo_root.resolve()
    if not _is_within(resolved_origin, resolved_root):
        raise RepositoryPythonError(
            f"repository source provenance failed: {package_name!r} expected under "
            f"{resolved_root}, resolved {resolved_origin}. Clear inherited PYTHONPATH/editable "
            "checkout state, run `make install`, and retry the repository-native target."
        )
    return resolved_origin


def repository_environment(
    *,
    repo_root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if environ is None else environ
    child_environment = dict(source)
    child_environment["PYTHONPATH"] = build_repository_pythonpath(
        repo_root=repo_root,
        inherited_pythonpath=source.get("PYTHONPATH", ""),
    )
    child_environment["LOTUS_REPOSITORY_ROOT"] = str(repo_root.resolve())
    return child_environment


def run_repository_python(
    arguments: Sequence[str],
    *,
    repo_root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run one Python command as argv, preserving its exit code and terminal streams."""

    if not arguments:
        raise RepositoryPythonError("repository Python launcher requires a command")
    child_environment = repository_environment(repo_root=repo_root, environ=environ)
    require_current_first_party_origin(
        repo_root=repo_root,
        pythonpath=child_environment["PYTHONPATH"],
    )
    completed = subprocess.run(
        [sys.executable, *arguments],
        cwd=repo_root.resolve(),
        env=child_environment,
        check=False,
        shell=False,
    )
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run_repository_python(tuple(sys.argv[1:] if argv is None else argv))
    except RepositoryPythonError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
