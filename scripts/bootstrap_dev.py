"""Install editable packages and dev tooling for local/CI quality gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS_FILE = ROOT / "constraints" / "shared-build-constraints.txt"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def constrained_pip_install(*args: str) -> None:
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-c",
            str(CONSTRAINTS_FILE),
            *args,
        ]
    )


def discover_editable_projects() -> list[Path]:
    pyprojects = sorted(ROOT.glob("src/**/pyproject.toml"))
    return [path.parent for path in pyprojects]


def main() -> int:
    projects = discover_editable_projects()
    for project_dir in projects:
        constrained_pip_install("-e", str(project_dir))

    constrained_pip_install("-r", "tests/requirements.txt")
    constrained_pip_install("ruff", "mypy", "pip-audit", "types-python-dateutil")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
