"""The Integration Full journal survives an abnormal pytest child exit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts.quality import pytest_progress_journal


def test_progress_journal_records_start_and_completed_phase(monkeypatch, tmp_path: Path) -> None:
    journal = tmp_path / "integration-progress.jsonl"
    monkeypatch.setenv("LOTUS_INTEGRATION_ALL_PROGRESS_PATH", str(journal))

    pytest_progress_journal.pytest_runtest_logstart(
        "tests/integration/test_x.py::test_x", ("", 1, "")
    )
    pytest_progress_journal.pytest_runtest_logreport(
        SimpleNamespace(
            nodeid="tests/integration/test_x.py::test_x",
            when="call",
            outcome="passed",
            duration=1.25,
        )
    )

    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["start", "phase"]
    assert [record["nodeid"] for record in records] == [
        "tests/integration/test_x.py::test_x",
        "tests/integration/test_x.py::test_x",
    ]
    assert records[1]["phase"] == "call"
    assert records[1]["outcome"] == "passed"
    assert records[1]["duration_seconds"] == 1.25


def test_progress_journal_is_inert_without_explicit_integration_path(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("LOTUS_INTEGRATION_ALL_PROGRESS_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    pytest_progress_journal.pytest_runtest_logstart(
        "tests/integration/test_x.py::test_x", ("", 1, "")
    )

    assert list(tmp_path.iterdir()) == []


def test_progress_journal_survives_actual_abnormal_pytest_exit(tmp_path: Path) -> None:
    test_file = tmp_path / "test_abrupt.py"
    test_file.write_text("import os\n\ndef test_abrupt():\n    os._exit(93)\n", encoding="utf-8")
    journal = tmp_path / "abrupt-progress.jsonl"
    environment = os.environ.copy()
    environment["LOTUS_INTEGRATION_ALL_PROGRESS_PATH"] = str(journal)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "scripts.quality.pytest_progress_journal",
            str(test_file),
        ],
        check=False,
        cwd=Path(__file__).resolve().parents[4],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 93
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "start"
    assert records[0]["nodeid"].endswith("test_abrupt.py::test_abrupt")
    assert not any(record.get("phase") == "call" for record in records)
