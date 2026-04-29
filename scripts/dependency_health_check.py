from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_LOCK_FILE = ROOT / "requirements" / "shared-runtime.lock.txt"
TEST_REQUIREMENTS_FILE = ROOT / "tests" / "requirements.txt"
TOOLING_LOCK_FILE = ROOT / "requirements" / "ci-tooling.lock.txt"
PIP_AUDIT_IGNORED_VULNERABILITIES = (
    # The audit venv's pip bootstrap is tooling-only and is not shipped with any Lotus service.
    "CVE-2026-3219",
)


def discover_editable_projects(root: Path = ROOT) -> list[Path]:
    return sorted(path.parent for path in root.glob("src/**/pyproject.toml"))


def venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def site_packages_path(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Lib" / "site-packages"
    return next((venv_dir / "lib").glob("python*/site-packages"))


def constrained_install_command(python_bin: Path, *install_args: str) -> list[str]:
    return [
        str(python_bin),
        "-m",
        "pip",
        "install",
        "-c",
        str(RUNTIME_LOCK_FILE),
        *install_args,
    ]


def pip_audit_command(python_bin: Path, site_packages_dir: Path) -> list[str]:
    ignored_vulnerabilities = [
        option
        for vulnerability_id in PIP_AUDIT_IGNORED_VULNERABILITIES
        for option in ("--ignore-vuln", vulnerability_id)
    ]
    return [
        str(python_bin),
        "-m",
        "pip_audit",
        "--path",
        str(site_packages_dir),
        *ignored_vulnerabilities,
    ]


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project-scoped dependency consistency and vulnerability validation"
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip vulnerability auditing and only run install consistency checks.",
    )
    args = parser.parse_args()

    temp_dir = Path(tempfile.mkdtemp(prefix="lotus-core-dependency-health-"))
    try:
        venv_dir = temp_dir / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python_bin = venv_python(venv_dir)

        _run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], cwd=ROOT)

        for project_dir in discover_editable_projects():
            _run(constrained_install_command(python_bin, "-e", str(project_dir)), cwd=ROOT)

        _run(
            constrained_install_command(python_bin, "-r", str(TEST_REQUIREMENTS_FILE)),
            cwd=ROOT,
        )
        _run(
            constrained_install_command(python_bin, "-r", str(TOOLING_LOCK_FILE)),
            cwd=ROOT,
        )
        _run([str(python_bin), "-m", "pip", "check"], cwd=ROOT)

        if not args.skip_audit:
            _run(
                pip_audit_command(python_bin, site_packages_path(venv_dir)),
                cwd=ROOT,
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
