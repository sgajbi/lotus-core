"""Tests for the portable Alembic migration contract validator."""

import subprocess
import sys
from pathlib import Path

from scripts.quality import migration_contract_check


def test_head_check_uses_active_python_interpreter(monkeypatch) -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="revision (head)\n", stderr="")

    monkeypatch.setattr(migration_contract_check.subprocess, "run", run)

    assert migration_contract_check._has_single_head() is True
    assert commands == [[sys.executable, "-m", "alembic", "heads"]]


def test_history_check_uses_active_python_interpreter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    alembic_dir = tmp_path / "alembic"
    versions_dir = alembic_dir / "versions"
    versions_dir.mkdir(parents=True)
    (versions_dir / "revision.py").write_text("revision = 'revision'\n", encoding="utf-8")
    migration_contract = tmp_path / "migration-contract.md"
    migration_contract.write_text("# Migration Contract\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(migration_contract_check, "ALEMBIC_DIR", alembic_dir)
    monkeypatch.setattr(migration_contract_check, "VERSIONS_DIR", versions_dir)
    monkeypatch.setattr(migration_contract_check, "REQUIRED_DOC", migration_contract)
    monkeypatch.setattr(migration_contract_check, "_has_single_head", lambda: True)
    monkeypatch.setattr(
        migration_contract_check,
        "_run",
        lambda command: commands.append(command) or 0,
    )

    assert migration_contract_check.run_alembic_sql_smoke() == 0
    assert commands == [[sys.executable, "-m", "alembic", "history"]]
