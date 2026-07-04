"""Remove governed local cache, build, coverage, and generated evidence artifacts."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PROTECTED_TRAVERSAL_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "ENV",
    "node_modules",
}

RECURSIVE_DISPOSABLE_DIR_NAMES = {
    "__pycache__",
    ".cache",
    ".hypothesis",
    ".import_linter_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".ipynb_checkpoints",
    "build",
    "dist",
    "htmlcov",
}

ROOT_DISPOSABLE_DIR_NAMES = {
    ".eggs",
    "develop-eggs",
    "downloads",
    "eggs",
    "output",
    "parts",
    "sdist",
    "var",
    "wheels",
}

DISPOSABLE_FILE_NAMES = {
    ".coverage",
    ".installed.cfg",
    "coverage.xml",
    "MANIFEST",
    "nosetests.xml",
    "pip-delete-this-directory.txt",
    "pip-log.txt",
}

DISPOSABLE_FILE_SUFFIXES = {
    ".cover",
    ".egg",
    ".manifest",
    ".pyc",
    ".pyo",
    ".so",
    ".spec",
    ".swp",
}

DISPOSABLE_FILE_PREFIXES = {
    ".coverage.",
}

DISPOSABLE_DIR_SUFFIXES = {
    ".egg-info",
}


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _ensure_safe_target(repo_root: Path, target: Path) -> None:
    repo_root_resolved = repo_root.resolve()
    target_absolute = target if target.is_absolute() else repo_root / target
    target_resolved = target_absolute.resolve(strict=False)
    if target_resolved == repo_root_resolved or not _is_relative_to(
        target_resolved, repo_root_resolved
    ):
        raise ValueError(f"Refusing to delete path outside repository root: {target}")


def _is_disposable_file(path: Path) -> bool:
    name = path.name
    return (
        name in DISPOSABLE_FILE_NAMES
        or any(name.startswith(prefix) for prefix in DISPOSABLE_FILE_PREFIXES)
        or any(name.endswith(suffix) for suffix in DISPOSABLE_FILE_SUFFIXES)
        or name.endswith(".pyc")
        or name.endswith(".pyo")
        or name.endswith(".pyd")
    )


def _is_disposable_dir(path: Path) -> bool:
    name = path.name
    return name in RECURSIVE_DISPOSABLE_DIR_NAMES or any(
        name.endswith(suffix) for suffix in DISPOSABLE_DIR_SUFFIXES
    )


def discover_cleanup_targets(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return disposable artifact paths without descending into protected directories."""

    root = repo_root.resolve()
    targets: list[Path] = []
    seen: set[Path] = set()

    for dirname in ROOT_DISPOSABLE_DIR_NAMES:
        path = root / dirname
        if path.exists():
            targets.append(path)
            seen.add(path)

    for current, dirnames, filenames in os.walk(root, topdown=True):
        current_path = Path(current)
        retained_dirs: list[str] = []
        for dirname in dirnames:
            child = current_path / dirname
            if dirname in PROTECTED_TRAVERSAL_DIR_NAMES:
                continue
            if _is_disposable_dir(child):
                if child not in seen:
                    targets.append(child)
                    seen.add(child)
                continue
            retained_dirs.append(dirname)
        dirnames[:] = retained_dirs

        for filename in filenames:
            child = current_path / filename
            if _is_disposable_file(child) and child not in seen:
                targets.append(child)
                seen.add(child)

    return sorted(targets)


def remove_cleanup_targets(
    *,
    repo_root: Path = REPO_ROOT,
    targets: Iterable[Path],
    dry_run: bool = False,
) -> list[Path]:
    root = repo_root.resolve()
    removed: list[Path] = []
    for target in sorted(targets):
        _ensure_safe_target(root, target)
        if not target.exists() and not target.is_symlink():
            continue
        removed.append(target)
        if dry_run:
            continue
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
    return removed


def clean_generated_artifacts(
    *,
    repo_root: Path = REPO_ROOT,
    dry_run: bool = False,
) -> list[Path]:
    targets = discover_cleanup_targets(repo_root=repo_root)
    return remove_cleanup_targets(repo_root=repo_root, targets=targets, dry_run=dry_run)


def _relative_paths(paths: Iterable[Path], repo_root: Path) -> list[str]:
    root = repo_root.resolve()
    return [path.resolve(strict=False).relative_to(root).as_posix() for path in paths]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove governed lotus-core local generated artifacts and caches."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to clean. Defaults to the lotus-core checkout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matched cleanup targets without deleting them.",
    )
    args = parser.parse_args(argv)

    removed = clean_generated_artifacts(repo_root=args.repo_root, dry_run=args.dry_run)
    action = "Would remove" if args.dry_run else "Removed"
    for relative_path in _relative_paths(removed, args.repo_root):
        print(relative_path)
    print(f"{action} {len(removed)} governed generated artifact(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
