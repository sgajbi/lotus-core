import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import dependency_health_check
from scripts.validation.dependency_health_cache import build_cache_identity, write_cache_marker

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_dependency_inputs(root: Path) -> None:
    (root / "requirements").mkdir(parents=True)
    (root / "requirements" / "shared-runtime.lock.txt").write_text(
        "fastapi==1.0\n",
        encoding="utf-8",
    )
    (root / "requirements" / "ci-tooling.lock.txt").write_text(
        "ruff==1.0\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "requirements.txt").write_text(
        "pytest==9.0\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='core'\n", encoding="utf-8")
    validation = root / "scripts" / "validation"
    validation.mkdir(parents=True)
    for filename in ("dependency_health_check.py", "dependency_health_cache.py"):
        (validation / filename).write_text(f"# {filename}\n", encoding="utf-8")


def _identity(root: Path):  # noqa: ANN202
    return build_cache_identity(
        root,
        installer_version="25.3",
        implementation_files=dependency_health_check._cache_implementation_files(root),
    )


def _create_fake_environment(venv_dir: Path) -> None:
    python_bin = dependency_health_check.venv_python(venv_dir)
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("fake-python", encoding="utf-8")
    if dependency_health_check.sys.platform != "win32":
        site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
        site_packages.mkdir(parents=True)


def test_discover_editable_projects_returns_sorted_project_roots(tmp_path: Path) -> None:
    alpha = tmp_path / "src" / "services" / "alpha_service"
    beta = tmp_path / "src" / "libs" / "beta_lib"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / "pyproject.toml").write_text("[project]\nname='alpha'\n", encoding="utf-8")
    (beta / "pyproject.toml").write_text("[project]\nname='beta'\n", encoding="utf-8")

    projects = dependency_health_check.discover_editable_projects(tmp_path)

    assert projects == [beta, alpha]


def test_constrained_install_command_uses_shared_runtime_lock() -> None:
    python_bin = Path("/tmp/python")
    command = dependency_health_check.constrained_install_command(
        python_bin,
        "-e",
        "src/services/query_service",
    )

    assert command[:6] == [
        str(python_bin),
        "-m",
        "pip",
        "install",
        "-c",
        str(dependency_health_check.RUNTIME_LOCK_FILE),
    ]
    assert command[-2:] == ["-e", "src/services/query_service"]


def test_pip_audit_command_scopes_to_site_packages_path_without_ignores() -> None:
    python_bin = Path("/tmp/python")
    site_packages = Path("/tmp/venv/site-packages")
    command = dependency_health_check.pip_audit_command(
        python_bin,
        site_packages,
    )

    assert command == [
        str(python_bin),
        "-m",
        "pip_audit",
        "--path",
        str(site_packages),
    ]


def test_tooling_lock_pins_secure_setuptools_bootstrap() -> None:
    tooling_requirements = dependency_health_check.TOOLING_LOCK_FILE.read_text(
        encoding="utf-8"
    ).splitlines()

    assert "setuptools==83.0.0" in tooling_requirements


def test_dependency_health_cli_supports_repo_native_direct_execution() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/validation/dependency_health_check.py",
            "--help",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--no-cache" in result.stdout


def test_dependency_health_cli_prints_canonical_cache_key_only() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/validation/dependency_health_check.py",
            "--print-cache-key",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) == 64
    assert set(result.stdout.strip()) <= set("0123456789abcdef")


def test_dependency_health_cache_miss_builds_and_publishes_verified_environment(
    tmp_path: Path,
) -> None:
    _write_dependency_inputs(tmp_path)
    cache_root = tmp_path / ".cache"
    report_path = tmp_path / "output" / "report.json"
    builds: list[Path] = []

    def builder(venv_dir: Path, **kwargs) -> None:  # noqa: ANN003
        builds.append(venv_dir)
        _create_fake_environment(venv_dir)

    report = dependency_health_check.run_dependency_health(
        root=tmp_path,
        cache_root=cache_root,
        report_path=report_path,
        skip_audit=True,
        installer_version="25.3",
        command_runner=lambda *args, **kwargs: None,
        environment_builder=builder,
        clock=lambda: 10.0,
    )

    cache_dir = cache_root / report.cache_key
    assert report.status == "passed"
    assert report.cache_status == "miss"
    assert report.cache_reason == "not_found"
    assert report.clean_install_performed is True
    assert len(builds) == 1
    assert (cache_dir / "dependency-health-cache.json").is_file()
    assert dependency_health_check.venv_python(cache_dir / "venv").is_file()
    assert '"cache_status": "miss"' in report_path.read_text(encoding="utf-8")


def test_dependency_health_cache_hit_rechecks_integrity_without_rebuilding(
    tmp_path: Path,
) -> None:
    _write_dependency_inputs(tmp_path)
    cache_root = tmp_path / ".cache"
    identity = _identity(tmp_path)
    cache_dir = cache_root / identity.key
    _create_fake_environment(cache_dir / "venv")
    write_cache_marker(cache_dir, identity)
    commands: list[list[str]] = []

    report = dependency_health_check.run_dependency_health(
        root=tmp_path,
        cache_root=cache_root,
        report_path=tmp_path / "report.json",
        skip_audit=True,
        installer_version="25.3",
        command_runner=lambda command, **kwargs: commands.append(command),
        environment_builder=lambda *args, **kwargs: pytest.fail("unexpected rebuild"),
    )

    assert report.cache_status == "hit"
    assert report.cache_reason == "integrity_verified"
    assert report.clean_install_performed is False
    assert commands == [
        [
            str(dependency_health_check.venv_python(cache_dir / "venv")),
            "-m",
            "pip",
            "check",
        ]
    ]


def test_dependency_health_cache_hit_runs_vulnerability_audit(tmp_path: Path) -> None:
    _write_dependency_inputs(tmp_path)
    cache_root = tmp_path / ".cache"
    identity = _identity(tmp_path)
    cache_dir = cache_root / identity.key
    _create_fake_environment(cache_dir / "venv")
    write_cache_marker(cache_dir, identity)
    commands: list[list[str]] = []

    report = dependency_health_check.run_dependency_health(
        root=tmp_path,
        cache_root=cache_root,
        report_path=tmp_path / "report.json",
        installer_version="25.3",
        command_runner=lambda command, **kwargs: commands.append(command),
        environment_builder=lambda *args, **kwargs: pytest.fail("unexpected rebuild"),
    )

    assert report.audit_executed is True
    assert commands[0][-3:] == ["-m", "pip", "check"]
    assert "pip_audit" in commands[1]
    assert "--path" in commands[1]


def test_dependency_health_corrupt_cache_is_invalidated_and_rebuilt(tmp_path: Path) -> None:
    _write_dependency_inputs(tmp_path)
    cache_root = tmp_path / ".cache"
    identity = _identity(tmp_path)
    corrupt_dir = cache_root / identity.key
    _create_fake_environment(corrupt_dir / "venv")
    (corrupt_dir / "dependency-health-cache.json").write_text("invalid", encoding="utf-8")
    build_count = 0

    def builder(venv_dir: Path, **kwargs) -> None:  # noqa: ANN003
        nonlocal build_count
        build_count += 1
        _create_fake_environment(venv_dir)

    report = dependency_health_check.run_dependency_health(
        root=tmp_path,
        cache_root=cache_root,
        report_path=tmp_path / "report.json",
        skip_audit=True,
        installer_version="25.3",
        command_runner=lambda *args, **kwargs: None,
        environment_builder=builder,
    )

    assert report.cache_status == "miss"
    assert report.cache_reason == "integrity_failed"
    assert build_count == 1
    assert (corrupt_dir / "dependency-health-cache.json").is_file()


def test_dependency_health_failed_install_is_not_published_as_cache(tmp_path: Path) -> None:
    _write_dependency_inputs(tmp_path)
    cache_root = tmp_path / ".cache"
    report_path = tmp_path / "report.json"

    def failing_builder(venv_dir: Path, **kwargs) -> None:  # noqa: ANN003
        raise subprocess.CalledProcessError(1, [str(venv_dir), "pip", "install"])

    with pytest.raises(subprocess.CalledProcessError):
        dependency_health_check.run_dependency_health(
            root=tmp_path,
            cache_root=cache_root,
            report_path=report_path,
            skip_audit=True,
            installer_version="25.3",
            command_runner=lambda *args, **kwargs: None,
            environment_builder=failing_builder,
        )

    identity = _identity(tmp_path)
    assert not (cache_root / identity.key).exists()
    assert list(cache_root.iterdir()) == []
    assert '"status": "failed"' in report_path.read_text(encoding="utf-8")


def test_dependency_health_no_cache_forces_disposable_clean_proof(tmp_path: Path) -> None:
    _write_dependency_inputs(tmp_path)
    cache_root = tmp_path / ".cache"
    identity = _identity(tmp_path)
    cache_dir = cache_root / identity.key
    _create_fake_environment(cache_dir / "venv")
    write_cache_marker(cache_dir, identity)
    original_marker = (cache_dir / "dependency-health-cache.json").read_bytes()
    builds = 0

    def builder(venv_dir: Path, **kwargs) -> None:  # noqa: ANN003
        nonlocal builds
        builds += 1
        _create_fake_environment(venv_dir)

    report = dependency_health_check.run_dependency_health(
        root=tmp_path,
        cache_root=cache_root,
        report_path=tmp_path / "report.json",
        skip_audit=True,
        no_cache=True,
        installer_version="25.3",
        command_runner=lambda *args, **kwargs: None,
        environment_builder=builder,
    )

    assert report.cache_status == "bypass"
    assert report.cache_reason == "operator_bypass"
    assert report.clean_install_requested is True
    assert report.clean_install_performed is True
    assert builds == 1
    assert (cache_dir / "dependency-health-cache.json").read_bytes() == original_marker
    assert [path.name for path in cache_root.iterdir()] == [identity.key]


def test_successful_parallel_staging_yields_to_verified_cache(tmp_path: Path) -> None:
    _write_dependency_inputs(tmp_path)
    identity = _identity(tmp_path)
    cache_dir = tmp_path / ".cache" / identity.key
    staging_dir = tmp_path / ".cache" / "staging"
    _create_fake_environment(cache_dir / "venv")
    write_cache_marker(cache_dir, identity)
    _create_fake_environment(staging_dir / "venv")

    selected = dependency_health_check._publish_successful_cache(
        staging_dir,
        cache_dir,
        identity,
        root=tmp_path,
        command_runner=lambda *args, **kwargs: None,
    )

    assert selected == cache_dir
    assert cache_dir.exists()
    assert not staging_dir.exists()
