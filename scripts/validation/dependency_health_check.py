from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Callable

try:
    from scripts.validation.dependency_health_cache import (
        DependencyHealthCacheIdentity,
        build_cache_identity,
        cache_marker_matches,
        write_cache_marker,
    )
except ModuleNotFoundError:
    from dependency_health_cache import (  # type: ignore[no-redef]
        DependencyHealthCacheIdentity,
        build_cache_identity,
        cache_marker_matches,
        write_cache_marker,
    )

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_LOCK_FILE = ROOT / "requirements" / "shared-runtime.lock.txt"
TEST_REQUIREMENTS_FILE = ROOT / "tests" / "requirements.txt"
TOOLING_LOCK_FILE = ROOT / "requirements" / "ci-tooling.lock.txt"
PIP_AUDIT_IGNORED_VULNERABILITIES: tuple[str, ...] = ()
DEFAULT_CACHE_ROOT = ROOT / ".cache" / "dependency-health"
DEFAULT_REPORT_FILE = ROOT / "output" / "dependency-health" / "report.json"


@dataclass(frozen=True)
class DependencyHealthReport:
    """Machine-readable evidence for one dependency-health execution."""

    schema_version: int
    status: str
    cache_key: str
    cache_status: str
    cache_reason: str
    duration_seconds: float
    clean_install_requested: bool
    clean_install_performed: bool
    audit_executed: bool
    installer_version: str
    python_identity: str
    platform_identity: str


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


def constrained_install_command(
    python_bin: Path,
    *install_args: str,
    constraint_file: Path = RUNTIME_LOCK_FILE,
) -> list[str]:
    return [
        str(python_bin),
        "-m",
        "pip",
        "install",
        "-c",
        str(constraint_file),
        *install_args,
    ]


def pip_audit_command(python_bin: Path, site_packages_dir: Path) -> list[str]:
    ignored_vulnerabilities = pip_audit_ignore_options()
    return [
        str(python_bin),
        "-m",
        "pip_audit",
        "--path",
        str(site_packages_dir),
        *ignored_vulnerabilities,
    ]


def pip_audit_ignore_options() -> list[str]:
    ignored_vulnerabilities = [
        option
        for vulnerability_id in PIP_AUDIT_IGNORED_VULNERABILITIES
        for option in ("--ignore-vuln", vulnerability_id)
    ]
    return ignored_vulnerabilities


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _cache_implementation_files(root: Path) -> tuple[Path, ...]:
    return (
        root / "scripts" / "validation" / "dependency_health_check.py",
        root / "scripts" / "validation" / "dependency_health_cache.py",
    )


def dependency_health_identity(
    *,
    root: Path = ROOT,
    installer_version: str | None = None,
) -> DependencyHealthCacheIdentity:
    """Resolve the canonical cache identity used by local and CI cache consumers."""
    resolved_root = root.resolve()
    return build_cache_identity(
        resolved_root,
        installer_version=installer_version or version("pip"),
        implementation_files=_cache_implementation_files(resolved_root),
    )


def _build_environment(
    venv_dir: Path,
    *,
    root: Path,
    installer_version: str,
    command_runner: Callable[..., None] = _run,
) -> None:
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    python_bin = venv_python(venv_dir)
    command_runner(
        [str(python_bin), "-m", "pip", "install", f"pip=={installer_version}"],
        cwd=root,
    )
    constraint_file = root / "requirements" / "shared-runtime.lock.txt"
    for project_dir in discover_editable_projects(root):
        command_runner(
            constrained_install_command(
                python_bin,
                "-e",
                str(project_dir),
                constraint_file=constraint_file,
            ),
            cwd=root,
        )
    for requirements_file in (
        root / "tests" / "requirements.txt",
        root / "requirements" / "ci-tooling.lock.txt",
    ):
        command_runner(
            constrained_install_command(
                python_bin,
                "-r",
                str(requirements_file),
                constraint_file=constraint_file,
            ),
            cwd=root,
        )
    command_runner([str(python_bin), "-m", "pip", "check"], cwd=root)


def _cache_is_usable(
    cache_dir: Path,
    identity: DependencyHealthCacheIdentity,
    *,
    root: Path,
    command_runner: Callable[..., None],
) -> bool:
    python_bin = venv_python(cache_dir / "venv")
    if not python_bin.is_file() or not cache_marker_matches(cache_dir, identity):
        return False
    try:
        command_runner([str(python_bin), "-m", "pip", "check"], cwd=root)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _publish_successful_cache(
    staging_dir: Path,
    cache_dir: Path,
    identity: DependencyHealthCacheIdentity,
    *,
    root: Path,
    command_runner: Callable[..., None],
) -> Path:
    write_cache_marker(staging_dir, identity)
    if not cache_dir.exists():
        staging_dir.replace(cache_dir)
        return cache_dir
    if _cache_is_usable(
        cache_dir,
        identity,
        root=root,
        command_runner=command_runner,
    ):
        shutil.rmtree(staging_dir, ignore_errors=True)
        return cache_dir
    shutil.rmtree(cache_dir, ignore_errors=True)
    staging_dir.replace(cache_dir)
    return cache_dir


def _write_report(report_path: Path, report: DependencyHealthReport) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(asdict(report), sort_keys=True))


def _build_report(
    *,
    status: str,
    identity: DependencyHealthCacheIdentity,
    cache_status: str,
    cache_reason: str,
    duration_seconds: float,
    no_cache: bool,
    clean_install_performed: bool,
    skip_audit: bool,
) -> DependencyHealthReport:
    return DependencyHealthReport(
        schema_version=1,
        status=status,
        cache_key=identity.key,
        cache_status=cache_status,
        cache_reason=cache_reason,
        duration_seconds=round(duration_seconds, 3),
        clean_install_requested=no_cache,
        clean_install_performed=clean_install_performed,
        audit_executed=not skip_audit,
        installer_version=identity.installer_version,
        python_identity=identity.python_identity,
        platform_identity=identity.platform_identity,
    )


def run_dependency_health(
    *,
    root: Path = ROOT,
    cache_root: Path | None = None,
    report_path: Path | None = None,
    skip_audit: bool = False,
    no_cache: bool = False,
    installer_version: str | None = None,
    command_runner: Callable[..., None] = _run,
    environment_builder: Callable[..., None] = _build_environment,
    clock: Callable[[], float] = time.perf_counter,
) -> DependencyHealthReport:
    """Validate dependency installation using only integrity-checked cache entries."""
    started_at = clock()
    resolved_root = root.resolve()
    resolved_cache_root = (
        cache_root or Path(os.getenv("LOTUS_DEPENDENCY_HEALTH_CACHE_DIR", DEFAULT_CACHE_ROOT))
    ).resolve()
    resolved_report_path = (report_path or DEFAULT_REPORT_FILE).resolve()
    identity = dependency_health_identity(
        root=resolved_root,
        installer_version=installer_version,
    )
    resolved_installer_version = identity.installer_version
    cache_dir = resolved_cache_root / identity.key
    resolved_cache_root.mkdir(parents=True, exist_ok=True)

    cache_status = "bypass" if no_cache else "miss"
    cache_reason = "operator_bypass" if no_cache else "not_found"
    clean_install_performed = False
    active_environment_root: Path | None = None
    disposable_environment_root: Path | None = None

    if not no_cache and cache_dir.exists():
        if _cache_is_usable(
            cache_dir,
            identity,
            root=resolved_root,
            command_runner=command_runner,
        ):
            cache_status = "hit"
            cache_reason = "integrity_verified"
            active_environment_root = cache_dir
        else:
            cache_reason = "integrity_failed"
            shutil.rmtree(cache_dir, ignore_errors=True)

    try:
        if active_environment_root is None:
            clean_install_performed = True
            staging_dir = Path(
                tempfile.mkdtemp(
                    prefix=f"{identity.key[:12]}-",
                    dir=resolved_cache_root,
                )
            )
            disposable_environment_root = staging_dir
            environment_builder(
                staging_dir / "venv",
                root=resolved_root,
                installer_version=resolved_installer_version,
                command_runner=command_runner,
            )
            if no_cache and cache_dir.exists():
                active_environment_root = staging_dir
            else:
                active_environment_root = _publish_successful_cache(
                    staging_dir,
                    cache_dir,
                    identity,
                    root=resolved_root,
                    command_runner=command_runner,
                )
                if active_environment_root == cache_dir:
                    disposable_environment_root = None

        python_bin = venv_python(active_environment_root / "venv")
        if not skip_audit:
            command_runner(
                pip_audit_command(
                    python_bin,
                    site_packages_path(active_environment_root / "venv"),
                ),
                cwd=resolved_root,
            )
    except Exception:
        report = _build_report(
            status="failed",
            identity=identity,
            cache_status=cache_status,
            cache_reason=cache_reason,
            duration_seconds=clock() - started_at,
            no_cache=no_cache,
            clean_install_performed=clean_install_performed,
            skip_audit=skip_audit,
        )
        _write_report(resolved_report_path, report)
        raise
    finally:
        if disposable_environment_root is not None:
            shutil.rmtree(disposable_environment_root, ignore_errors=True)

    report = _build_report(
        status="passed",
        identity=identity,
        cache_status=cache_status,
        cache_reason=cache_reason,
        duration_seconds=clock() - started_at,
        no_cache=no_cache,
        clean_install_performed=clean_install_performed,
        skip_audit=skip_audit,
    )
    _write_report(resolved_report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project-scoped dependency consistency and vulnerability validation"
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip vulnerability auditing and only run install consistency checks.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force a clean bootstrap without reusing an existing cache entry.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Override the content-addressed dependency-health cache root.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Override the machine-readable dependency-health report path.",
    )
    parser.add_argument(
        "--print-cache-key",
        action="store_true",
        help="Print the canonical cache key without creating or validating an environment.",
    )
    args = parser.parse_args()

    if args.print_cache_key:
        print(dependency_health_identity().key)
        return 0

    run_dependency_health(
        skip_audit=args.skip_audit,
        no_cache=args.no_cache,
        cache_root=args.cache_dir,
        report_path=args.report,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
