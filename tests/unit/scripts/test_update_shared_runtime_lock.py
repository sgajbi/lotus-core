"""Tests for deterministic shared runtime lock generation."""

from pathlib import Path

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
    monkeypatch.setattr(lock_module, "RUNTIME_INPUT", tmp_path / "runtime.in")
    monkeypatch.setattr(lock_module, "RUNTIME_LOCK", tmp_path / "runtime.lock")
    monkeypatch.setattr(lock_module.tempfile, "mkdtemp", lambda **_kwargs: str(tmp_path / "tools"))
    monkeypatch.setattr(
        lock_module,
        "_run",
        lambda command, **_kwargs: commands.append(command),
    )

    lock_module._compile_runtime_lock(upgrade_packages=("click", "urllib3"))

    compile_command = commands[-1]
    assert compile_command.count("--upgrade-package") == 2
    assert compile_command[compile_command.index("--upgrade-package") + 1] == "click"
    assert "urllib3" in compile_command
    assert compile_command[-2:] == [
        str(tmp_path / "runtime.lock"),
        str(tmp_path / "runtime.in"),
    ]
