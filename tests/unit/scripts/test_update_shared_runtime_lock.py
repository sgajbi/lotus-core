"""Tests for deterministic shared runtime lock generation."""

from pathlib import Path

import pytest

from scripts.development import update_shared_runtime_lock as lock_module


def _write_project(
    root: Path,
    relative_path: str,
    *,
    name: str,
    dependencies: list[str],
) -> None:
    project = root / relative_path
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text(
        "\n".join(
            (
                "[project]",
                f'name = "{name}"',
                'version = "0.1.0"',
                "dependencies = [",
                *(f'  "{dependency}",' for dependency in dependencies),
                "]",
            )
        ),
        encoding="utf-8",
    )


def test_collect_runtime_dependencies_excludes_local_projects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_project(
        tmp_path,
        "src/libs/portfolio-common/pyproject.toml",
        name="portfolio-common",
        dependencies=["pydantic==2.13.4"],
    )
    _write_project(
        tmp_path,
        "src/services/transaction-processing/pyproject.toml",
        name="portfolio-transaction-processing-service",
        dependencies=["portfolio_common==0.1.0", "uvicorn[standard]==0.49.0"],
    )
    monkeypatch.setattr(lock_module, "REPO_ROOT", tmp_path)

    assert lock_module._collect_runtime_dependencies() == [
        "pydantic==2.13.4",
        "uvicorn[standard]==0.49.0",
    ]


def test_compile_runtime_lock_forwards_bounded_package_upgrades(
    tmp_path: Path,
    monkeypatch,
) -> None:
    commands: list[list[str]] = []
    (tmp_path / "runtime.in").write_text("demo==1.0\n", encoding="utf-8")
    (tmp_path / "runtime.lock").write_text("demo==1.0\n", encoding="utf-8")
    monkeypatch.setattr(lock_module, "RUNTIME_INPUT", tmp_path / "runtime.in")
    monkeypatch.setattr(lock_module, "RUNTIME_LOCK", tmp_path / "runtime.lock")
    tools = tmp_path / "tools"
    tools.mkdir()
    monkeypatch.setattr(lock_module.tempfile, "mkdtemp", lambda **_kwargs: str(tools))
    monkeypatch.setattr(
        lock_module.subprocess,
        "run",
        lambda command, **_kwargs: (
            commands.append(command),
            (tools / "shared-runtime.lock.txt").write_text(
                "demo==1.0\n    # via /work/shared-runtime.in\n", encoding="utf-8"
            ),
        )[-1],
    )

    result = lock_module._compile_linux_runtime_lock(upgrade_packages=("click", "urllib3"))

    compile_command = commands[-1][-1]
    assert "--upgrade-package click --upgrade-package urllib3" in compile_command
    assert "Python 3.11; platform linux/amd64" in result
    assert "/work/" not in result


def test_normalized_runtime_lock_is_replay_stable() -> None:
    raw = "# generated on a workstation\ndemo==1.0\n    # via /work/shared-runtime.in\n"

    first = lock_module._normalize_compiled_lock(raw, platform="linux/amd64")
    second = lock_module._normalize_compiled_lock(raw, platform="linux/amd64")
    assert first == second
    assert "pip==26.1.2; pip-tools==7.5.3" in first


def test_compile_runtime_lock_rejects_shell_control_in_upgrade_name() -> None:
    with pytest.raises(SystemExit, match="Invalid --upgrade-package"):
        lock_module._compile_linux_runtime_lock(upgrade_packages=("uvicorn;echo-unsafe",))
