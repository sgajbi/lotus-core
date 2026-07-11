"""Protect service wheel discovery for the runtime `app` package namespace."""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = REPO_ROOT / "src" / "services"


def _service_projects() -> list[Path]:
    return sorted(SERVICES_ROOT.rglob("pyproject.toml"))


def test_service_wheels_include_the_runtime_app_namespace() -> None:
    projects = _service_projects()
    assert projects

    failures: list[str] = []
    for project_path in projects:
        service_root = project_path.parent
        if not (service_root / "app" / "__init__.py").is_file():
            continue
        project = tomllib.loads(project_path.read_text(encoding="utf-8"))
        package_find = project.get("tool", {}).get("setuptools", {}).get("packages", {}).get("find")
        where = package_find.get("where", []) if isinstance(package_find, dict) else []
        include = package_find.get("include", []) if isinstance(package_find, dict) else []
        includes_app = any(fnmatch.fnmatch("app", pattern) for pattern in include)
        if where != ["."] or not includes_app:
            failures.append(project_path.relative_to(REPO_ROOT).as_posix())

    assert failures == [], (
        "service wheels must discover the runtime app namespace from the service root: "
        + ", ".join(failures)
    )
