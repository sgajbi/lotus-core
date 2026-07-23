"""Reject first-party imports that resolve outside the invoking Core checkout."""

from __future__ import annotations

import importlib.machinery
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

PROTECTED_TOP_LEVEL_PACKAGES = frozenset({"app", "portfolio_common"})


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _editable_mapping(
    finder: Any,
    *,
    modules: Mapping[str, ModuleType] | None = None,
) -> Mapping[str, str]:
    module_name = getattr(finder, "__module__", "")
    if not module_name.startswith("__editable__"):
        return {}
    loaded_modules = sys.modules if modules is None else modules
    module = loaded_modules.get(module_name)
    if module is None:
        return {}
    mapping = getattr(module, "MAPPING", {})
    return mapping if isinstance(mapping, Mapping) else {}


def filter_foreign_editable_finders(
    meta_path: Sequence[Any],
    *,
    repo_root: Path,
    modules: Mapping[str, ModuleType] | None = None,
) -> list[Any]:
    """Remove editable finders that can claim protected names from another checkout."""

    retained: list[Any] = []
    for finder in meta_path:
        mapping = _editable_mapping(finder, modules=modules)
        protected_paths = (
            Path(source_path)
            for package_name, source_path in mapping.items()
            if package_name in PROTECTED_TOP_LEVEL_PACKAGES
        )
        if any(not _is_within(path, repo_root) for path in protected_paths):
            continue
        retained.append(finder)
    return retained


class RepositoryFirstPartyImportGuard:
    """Fail closed when normal path lookup finds a foreign first-party package."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def find_spec(self, fullname: str, path=None, target=None):  # noqa: ANN001, ANN201, ARG002
        if "." in fullname or fullname not in PROTECTED_TOP_LEVEL_PACKAGES:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None:
            return None
        locations = tuple(spec.submodule_search_locations or ())
        resolved_paths = [Path(location).resolve() for location in locations]
        if spec.origin and spec.origin not in {"built-in", "frozen"}:
            resolved_paths.append(Path(spec.origin).resolve())
        foreign_paths = [path for path in resolved_paths if not _is_within(path, self.repo_root)]
        if foreign_paths:
            rendered = ", ".join(str(path) for path in foreign_paths)
            raise ImportError(
                "repository source provenance failed: "
                f"{fullname!r} resolved outside {self.repo_root}: {rendered}. "
                "Run `make install` from the intended lotus-core checkout."
            )
        return None


def activate_repository_import_guard(repo_root: Path) -> None:
    """Sanitize editable hooks and install an actual-import ownership fence."""

    resolved_root = repo_root.resolve()
    sys.meta_path[:] = filter_foreign_editable_finders(
        sys.meta_path,
        repo_root=resolved_root,
    )
    if not any(
        isinstance(finder, RepositoryFirstPartyImportGuard) and finder.repo_root == resolved_root
        for finder in sys.meta_path
    ):
        sys.meta_path.insert(0, RepositoryFirstPartyImportGuard(resolved_root))
