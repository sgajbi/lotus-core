"""Install editable packages and dev tooling for local/CI quality gates."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

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


def require_portfolio_common_editable_origin(
    *,
    expected_project: Path = PORTFOLIO_COMMON_PROJECT,
    distribution_resolver: Callable[[str], Distribution] = distribution,
) -> Path:
    """Prove bootstrap left the shared first-party distribution bound to this checkout."""

    try:
        installed = distribution_resolver("portfolio-common")
    except PackageNotFoundError as exc:
        raise RuntimeError("portfolio-common is not installed after repository bootstrap") from exc
    direct_url_text = installed.read_text("direct_url.json")
    if not direct_url_text:
        raise RuntimeError("portfolio-common install has no editable direct_url.json provenance")
    payload = json.loads(direct_url_text)
    if payload.get("dir_info", {}).get("editable") is not True:
        raise RuntimeError("portfolio-common install is not editable after repository bootstrap")
    parsed_url = urlparse(str(payload.get("url", "")))
    if parsed_url.scheme != "file":
        raise RuntimeError("portfolio-common editable provenance must use a local file URL")
    installed_project = Path(url2pathname(unquote(parsed_url.path))).resolve()
    expected = expected_project.resolve()
    if installed_project != expected:
        raise RuntimeError(
            "portfolio-common editable provenance points outside the invoking worktree: "
            f"expected {expected}, found {installed_project}. Run `make install` from the "
            "intended lotus-core checkout."
        )
    return installed_project


def main() -> int:
    projects = discover_editable_projects()
    for project_dir in projects:
        constrained_pip_install("-e", str(project_dir))

    constrained_pip_install("-r", "tests/requirements.txt")
    constrained_pip_install("-r", str(TOOLING_LOCK_FILE))
    require_portfolio_common_editable_origin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
