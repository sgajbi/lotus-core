from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality import ci_tooling


def _lock(tmp_path: Path, content: str) -> Path:
    lock_file = tmp_path / "ci-tooling.lock.txt"
    lock_file.write_text(content, encoding="utf-8")
    return lock_file


def test_exact_pin_loading_normalizes_distribution_names(tmp_path: Path) -> None:
    lock_file = _lock(tmp_path, "# governed\nImport_Linter==2.12\nruff==0.15.18\n")

    assert ci_tooling.load_exact_pins(lock_file) == {
        "import-linter": "2.12",
        "ruff": "0.15.18",
    }


@pytest.mark.parametrize(
    "content",
    [
        "ruff>=0.15.18\n",
        "ruff\n",
        "ruff==0.15.18\nruff==0.15.19\n",
    ],
)
def test_lock_rejects_ranges_unpinned_tools_and_duplicates(
    tmp_path: Path,
    content: str,
) -> None:
    with pytest.raises(ci_tooling.ToolingContractError):
        ci_tooling.load_exact_pins(_lock(tmp_path, content))


def test_active_interpreter_must_match_exact_pin(tmp_path: Path) -> None:
    lock_file = _lock(tmp_path, "ruff==0.15.18\n")

    assert (
        ci_tooling.require_pinned_tool(
            "ruff",
            lock_file=lock_file,
            version_resolver=lambda _: "0.15.18",
        )
        == "0.15.18"
    )
    with pytest.raises(ci_tooling.ToolingContractError, match="active interpreter has 0.15.21"):
        ci_tooling.require_pinned_tool(
            "ruff",
            lock_file=lock_file,
            version_resolver=lambda _: "0.15.21",
        )


def test_missing_tool_diagnostic_has_deterministic_cross_platform_remediation(
    tmp_path: Path,
) -> None:
    lock_file = _lock(tmp_path, "ruff==0.15.18\n")

    def missing(_: str) -> str:
        raise ci_tooling.PackageNotFoundError("ruff")

    with pytest.raises(ci_tooling.ToolingContractError) as raised:
        ci_tooling.require_pinned_tool(
            "ruff",
            lock_file=lock_file,
            version_resolver=missing,
        )

    message = str(raised.value)
    assert "active interpreter has not installed" in message
    assert "make install" in message
    assert "worktree-fenced Make entry point" in message


@pytest.mark.parametrize(
    ("python_executable", "expected"),
    [
        (
            r"C:\Program Files\Python312\python.exe",
            [r"C:\Program Files\Python312\python.exe", "-m", "ruff", "check", "."],
        ),
        ("/usr/bin/python3", ["/usr/bin/python3", "-m", "ruff", "check", "."]),
    ],
)
def test_module_command_is_an_os_neutral_argv_without_shell_quoting(
    python_executable: str,
    expected: list[str],
) -> None:
    assert (
        ci_tooling.build_module_command(
            "ruff",
            ["check", "."],
            python_executable=python_executable,
        )
        == expected
    )


def test_runner_verifies_and_executes_in_same_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], Path, bool]] = []
    monkeypatch.setattr(ci_tooling, "require_pinned_tool", lambda *args, **kwargs: "0.15.18")

    def run(command: list[str], *, cwd: Path, check: bool) -> SimpleNamespace:
        calls.append((command, cwd, check))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(subprocess, "run", run)

    assert ci_tooling.run_pinned_tool("ruff", ["check", "."]) == 7
    assert calls == [
        ([ci_tooling.sys.executable, "-m", "ruff", "check", "."], ci_tooling.ROOT, False)
    ]
