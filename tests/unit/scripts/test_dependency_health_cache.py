"""Contract tests for dependency-health cache identity and integrity markers."""

from __future__ import annotations

from pathlib import Path

from scripts.validation.dependency_health_cache import (
    CACHE_MARKER_FILE,
    build_cache_identity,
    cache_marker_matches,
    discover_cache_inputs,
    write_cache_marker,
)


def _write_cache_inputs(root: Path) -> tuple[Path, Path]:
    service_project = root / "src" / "services" / "query" / "pyproject.toml"
    service_project.parent.mkdir(parents=True)
    service_project.write_text("[project]\nname='query'\n", encoding="utf-8")
    requirements = root / "requirements" / "shared-runtime.lock.txt"
    requirements.parent.mkdir(parents=True)
    requirements.write_text("fastapi==1.0\n", encoding="utf-8")
    test_requirements = root / "tests" / "requirements.txt"
    test_requirements.parent.mkdir(parents=True)
    test_requirements.write_text("pytest==9.0\n", encoding="utf-8")
    root_project = root / "pyproject.toml"
    root_project.write_text("[project]\nname='root'\n", encoding="utf-8")
    implementation = root / "scripts" / "validation" / "dependency_health_check.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("CACHE_POLICY = 1\n", encoding="utf-8")
    return service_project, implementation


def test_discover_cache_inputs_covers_dependency_packaging_and_policy_files(tmp_path: Path) -> None:
    service_project, implementation = _write_cache_inputs(tmp_path)

    inputs = discover_cache_inputs(tmp_path, implementation_files=(implementation,))

    assert inputs == tuple(
        sorted(
            path.resolve()
            for path in {
                tmp_path / "pyproject.toml",
                tmp_path / "requirements" / "shared-runtime.lock.txt",
                tmp_path / "tests" / "requirements.txt",
                service_project,
                implementation,
            }
        )
    )


def test_cache_identity_is_deterministic_and_content_addressed(tmp_path: Path) -> None:
    service_project, implementation = _write_cache_inputs(tmp_path)
    identity_options = {
        "installer_version": "25.3",
        "implementation_files": (implementation,),
        "python_identity": "cpython:3.12.10:cpython-312",
        "platform_identity": "Linux:x86_64:linux",
    }

    first = build_cache_identity(tmp_path, **identity_options)
    second = build_cache_identity(tmp_path, **identity_options)
    service_project.write_text(
        "[project]\nname='query'\ndependencies=['httpx']\n",
        encoding="utf-8",
    )
    changed = build_cache_identity(tmp_path, **identity_options)

    assert first == second
    assert len(first.key) == 64
    assert changed.key != first.key


def test_cache_identity_changes_with_interpreter_platform_and_installer(tmp_path: Path) -> None:
    _, implementation = _write_cache_inputs(tmp_path)
    common = {
        "root": tmp_path,
        "implementation_files": (implementation,),
    }

    baseline = build_cache_identity(
        **common,
        installer_version="25.3",
        python_identity="cpython:3.12.10:cpython-312",
        platform_identity="Linux:x86_64:linux",
    )

    assert (
        build_cache_identity(
            **common,
            installer_version="25.2",
            python_identity=baseline.python_identity,
            platform_identity=baseline.platform_identity,
        ).key
        != baseline.key
    )
    assert (
        build_cache_identity(
            **common,
            installer_version=baseline.installer_version,
            python_identity="cpython:3.13.3:cpython-313",
            platform_identity=baseline.platform_identity,
        ).key
        != baseline.key
    )
    assert (
        build_cache_identity(
            **common,
            installer_version=baseline.installer_version,
            python_identity=baseline.python_identity,
            platform_identity="Windows:AMD64:win32",
        ).key
        != baseline.key
    )


def test_cache_marker_requires_exact_valid_json_identity(tmp_path: Path) -> None:
    _, implementation = _write_cache_inputs(tmp_path)
    identity = build_cache_identity(
        tmp_path,
        installer_version="25.3",
        implementation_files=(implementation,),
        python_identity="cpython:3.12.10:cpython-312",
        platform_identity="Linux:x86_64:linux",
    )
    cache_dir = tmp_path / ".cache" / identity.key
    cache_dir.mkdir(parents=True)

    assert cache_marker_matches(cache_dir, identity) is False

    (cache_dir / CACHE_MARKER_FILE).write_text("not-json", encoding="utf-8")
    assert cache_marker_matches(cache_dir, identity) is False

    write_cache_marker(cache_dir, identity)
    assert cache_marker_matches(cache_dir, identity) is True

    marker = cache_dir / CACHE_MARKER_FILE
    marker.write_text(marker.read_text(encoding="utf-8").replace(identity.key, "0" * 64))
    assert cache_marker_matches(cache_dir, identity) is False
