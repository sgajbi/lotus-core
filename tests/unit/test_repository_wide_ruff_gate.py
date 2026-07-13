"""Regression tests for repository-wide Ruff enforcement."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_ruff(working_directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ruff", *arguments],
        cwd=working_directory,
        check=False,
        capture_output=True,
        text=True,
    )


def test_repository_wide_ruff_handles_add_rename_delete_and_spaces(tmp_path: Path) -> None:
    added = tmp_path / "src" / "new package" / "added_module.py"
    added.parent.mkdir(parents=True)
    added.write_text("import os\n", encoding="utf-8")

    added_result = _run_ruff(tmp_path, "check", ".", "--isolated")
    assert added_result.returncode == 1
    assert "added_module.py" in added_result.stdout

    renamed = tmp_path / "src" / "renamed package" / "renamed_module.py"
    renamed.parent.mkdir(parents=True)
    added.rename(renamed)

    renamed_result = _run_ruff(tmp_path, "check", ".", "--isolated")
    assert renamed_result.returncode == 1
    assert "renamed_module.py" in renamed_result.stdout

    renamed.unlink()

    deleted_result = _run_ruff(tmp_path, "check", ".", "--isolated")
    assert deleted_result.returncode == 0


def test_repository_wide_format_gate_detects_space_containing_paths(tmp_path: Path) -> None:
    module = tmp_path / "src" / "new package" / "format_me.py"
    module.parent.mkdir(parents=True)
    module.write_text("values=[1,2,3]\n", encoding="utf-8")
    transaction_module = (
        tmp_path
        / "src"
        / "services"
        / "portfolio_transaction_processing_service"
        / "app"
        / "domain"
        / "cashflow_policy.py"
    )
    transaction_module.parent.mkdir(parents=True)
    transaction_module.write_text("values=[1,2,3]\n", encoding="utf-8")

    result = _run_ruff(tmp_path, "format", "--check", ".", "--isolated")

    assert result.returncode == 1
    assert "format_me.py" in result.stdout
    assert "cashflow_policy.py" in result.stdout
