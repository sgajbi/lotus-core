from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts.development import repository_python
from scripts.development.repository_import_guard import filter_foreign_editable_finders


def _package_root(repo_root: Path) -> Path:
    package_root = repo_root / "src" / "libs" / "portfolio-common" / "portfolio_common"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text("SOURCE = 'current'\n", encoding="utf-8")
    return package_root


def test_repository_pythonpath_discards_foreign_core_worktree(tmp_path: Path) -> None:
    current = tmp_path / "lotus-core-current"
    foreign = tmp_path / "lotus-core-other" / "src" / "libs" / "portfolio-common"
    unrelated = tmp_path / "shared-python"
    _package_root(current)
    foreign.mkdir(parents=True)
    unrelated.mkdir()

    pythonpath = repository_python.build_repository_pythonpath(
        repo_root=current,
        inherited_pythonpath=os.pathsep.join((str(foreign), str(unrelated))),
    )
    entries = pythonpath.split(os.pathsep)

    assert entries[:3] == [
        str(repository_python.STARTUP_GUARD_ROOT.resolve()),
        str((current / "src" / "libs" / "portfolio-common").resolve()),
        str(current.resolve()),
    ]
    assert str(foreign.resolve()) not in entries
    assert str(unrelated.resolve()) in entries


def test_current_first_party_origin_reports_expected_and_actual_paths(tmp_path: Path) -> None:
    current = tmp_path / "lotus-core-current"
    foreign_root = tmp_path / "external-source"
    foreign_package = foreign_root / "portfolio_common"
    current.mkdir()
    foreign_package.mkdir(parents=True)
    (foreign_package / "__init__.py").write_text("", encoding="utf-8")

    with pytest.raises(repository_python.RepositoryPythonError) as raised:
        repository_python.require_current_first_party_origin(
            repo_root=current,
            pythonpath=str(foreign_root),
        )

    message = str(raised.value)
    assert str(current.resolve()) in message
    assert str((foreign_package / "__init__.py").resolve()) in message
    assert "make install" in message


def test_repository_launcher_loads_distinguishable_current_source(tmp_path: Path) -> None:
    current = tmp_path / "lotus-core-current"
    foreign = tmp_path / "lotus-core-other"
    _package_root(current)
    foreign_package = _package_root(foreign)
    (foreign_package / "__init__.py").write_text("SOURCE = 'foreign'\n", encoding="utf-8")
    output_path = tmp_path / "resolved.txt"
    command = (
        "import pathlib, portfolio_common; "
        f"pathlib.Path({str(output_path)!r}).write_text("
        "portfolio_common.SOURCE + '\\n' + portfolio_common.__file__, encoding='utf-8')"
    )

    result = repository_python.run_repository_python(
        ("-c", command),
        repo_root=current,
        environ={"PYTHONPATH": str(foreign_package.parent)},
    )

    source, resolved_path = output_path.read_text(encoding="utf-8").splitlines()
    assert result == 0
    assert source == "current"
    assert Path(resolved_path).resolve().is_relative_to(current.resolve())


def test_repository_launcher_rejects_physical_foreign_app_from_user_site(
    tmp_path: Path,
) -> None:
    current = Path(__file__).resolve().parents[3]
    user_base = tmp_path / "foreign-user-base"
    environment = {**os.environ, "PYTHONUSERBASE": str(user_base), "PYTHONPATH": ""}
    user_site = Path(
        subprocess.check_output(
            [sys.executable, "-c", "import site; print(site.getusersitepackages())"],
            env=environment,
            text=True,
        ).strip()
    )
    foreign_app = user_site / "app"
    foreign_app.mkdir(parents=True)
    (foreign_app / "__init__.py").write_text("SOURCE = 'foreign'\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(current / "scripts/development/repository_python.py"),
            "-c",
            "import app",
        ],
        cwd=current,
        env={
            **environment,
            "PYTHONPATH": str(current),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "repository source provenance failed" in completed.stderr
    assert str(foreign_app.resolve()) in completed.stderr


def test_repository_launcher_allows_explicit_current_service_app(tmp_path: Path) -> None:
    current = tmp_path / "lotus-core-current"
    _package_root(current)
    service_root = current / "src" / "services" / "example_service"
    current_app = service_root / "app"
    current_app.mkdir(parents=True)
    (current_app / "__init__.py").write_text("SOURCE = 'current'\n", encoding="utf-8")
    output_path = tmp_path / "app-origin.txt"

    result = repository_python.run_repository_python(
        (
            "-c",
            "import app, pathlib; "
            f"pathlib.Path({str(output_path)!r}).write_text(app.__file__, encoding='utf-8')",
        ),
        repo_root=current,
        environ={"PYTHONPATH": str(service_root)},
    )

    assert result == 0
    assert Path(output_path.read_text(encoding="utf-8")).resolve().is_relative_to(current.resolve())


def test_foreign_editable_app_finder_is_removed(tmp_path: Path) -> None:
    current = tmp_path / "lotus-core-current"
    foreign = tmp_path / "lotus-core-other" / "src" / "services" / "example" / "app"
    foreign_module_name = "__editable___foreign_service_finder"
    foreign_module = ModuleType(foreign_module_name)
    foreign_module.MAPPING = {"app": str(foreign)}  # type: ignore[attr-defined]
    current_module_name = "__editable___current_common_finder"
    current_module = ModuleType(current_module_name)
    current_module.MAPPING = {  # type: ignore[attr-defined]
        "portfolio_common": str(current / "src/libs/portfolio-common/portfolio_common")
    }

    class ForeignEditableFinder:
        pass

    ForeignEditableFinder.__module__ = foreign_module_name

    class CurrentEditableFinder:
        pass

    CurrentEditableFinder.__module__ = current_module_name
    foreign_finder = ForeignEditableFinder()
    current_finder = CurrentEditableFinder()
    ordinary_finder = object()

    assert filter_foreign_editable_finders(
        [foreign_finder, current_finder, ordinary_finder],
        repo_root=current,
        modules={
            foreign_module_name: foreign_module,
            current_module_name: current_module,
        },
    ) == [current_finder, ordinary_finder]


def test_repository_launcher_uses_argv_without_shell_and_propagates_exit(
    monkeypatch,
) -> None:
    observed: dict[str, object] = {}

    def _run(command, **kwargs):
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(repository_python.subprocess, "run", _run)

    assert repository_python.run_repository_python(("-c", "pass")) == 7
    assert observed["command"] == [sys.executable, "-c", "pass"]
    assert observed["cwd"] == repository_python.ROOT
    assert observed["shell"] is False
    assert observed["check"] is False
    assert observed["env"]["LOTUS_REPOSITORY_ROOT"] == str(repository_python.ROOT)


def test_repository_launcher_requires_a_command() -> None:
    with pytest.raises(repository_python.RepositoryPythonError, match="requires a command"):
        repository_python.run_repository_python(())


def test_make_python_recipes_use_repository_launcher() -> None:
    makefile_lines = Path("Makefile").read_text(encoding="utf-8").splitlines()

    assert "REPOSITORY_PYTHON := python scripts/development/repository_python.py" in makefile_lines
    assert not [line for line in makefile_lines if line.startswith("\tpython ")]
    assert [line for line in makefile_lines if line.startswith("\t$(REPOSITORY_PYTHON) ")]
