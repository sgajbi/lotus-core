"""Install editable packages and dev tooling for local/CI quality gates."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_LOCK_FILE = ROOT / "requirements" / "shared-runtime.lock.txt"
TOOLING_LOCK_FILE = ROOT / "requirements" / "ci-tooling.lock.txt"
PORTFOLIO_COMMON_PROJECT = ROOT / "src" / "libs" / "portfolio-common"


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
            str(RUNTIME_LOCK_FILE),
            *args,
        ]
    )


def discover_editable_projects() -> list[Path]:
    pyprojects = sorted(ROOT.glob("src/**/pyproject.toml"))
    return [path.parent for path in pyprojects]


def resolve_installed_portfolio_common_origin() -> Path:
    """Resolve the installed package without inheriting checkout-specific Python paths."""

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-P",
            "-c",
            (
                "from pathlib import Path; import portfolio_common; "
                "print(Path(portfolio_common.__file__).resolve())"
            ),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic"
        raise RuntimeError(
            "portfolio-common is not importable after repository bootstrap: " + detail
        )
    origin = result.stdout.strip()
    if not origin:
        raise RuntimeError("portfolio-common bootstrap import returned no source origin")
    return Path(origin).resolve()


def require_portfolio_common_import_origin(
    *,
    expected_project: Path = PORTFOLIO_COMMON_PROJECT,
    origin_resolver: Callable[[], Path] = resolve_installed_portfolio_common_origin,
) -> Path:
    """Prove an isolated child interpreter imports shared code from this checkout."""

    installed_origin = origin_resolver().resolve()
    expected_package = (expected_project / "portfolio_common").resolve()
    if not installed_origin.is_relative_to(expected_package):
        raise RuntimeError(
            "portfolio-common import provenance points outside the invoking worktree: "
            f"expected source under {expected_package}, found {installed_origin}. "
            "Run `make install` from the "
            "intended lotus-core checkout."
        )
    return installed_origin


def main() -> int:
    projects = discover_editable_projects()
    for project_dir in projects:
        constrained_pip_install("-e", str(project_dir))

    constrained_pip_install("-r", "tests/requirements.txt")
    constrained_pip_install("-r", str(TOOLING_LOCK_FILE))
    require_portfolio_common_import_origin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
