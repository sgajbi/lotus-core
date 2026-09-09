from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.release import audit_main_gate_coverage as audit


def attempt(
    conclusion: str = "success",
    *,
    status: str = "completed",
    run_id: int = 1,
    attempt_number: int = 1,
    started_at: str = "2026-09-09T00:00:00Z",
) -> dict[str, object]:
    return {
        "conclusion": conclusion,
        "status": status,
        "run_id": run_id,
        "attempt": attempt_number,
        "started_at": started_at,
        "url": f"https://github.example/actions/runs/{run_id}",
    }


def test_missing_cancelled_and_pending_runs_fail_closed() -> None:
    assert audit.classify([]).state == audit.UNGATED
    assert audit.classify(None).state == audit.UNVERIFIABLE
    assert audit.classify([attempt("cancelled")]).state == audit.UNVERIFIABLE
    assert audit.classify([attempt("", status="in_progress")]).state == audit.UNVERIFIABLE


def test_failure_is_a_verdict_and_a_later_success_preserves_recovery_history() -> None:
    failing = attempt("failure", run_id=7)
    recovered = attempt(
        "success",
        run_id=8,
        started_at="2026-09-09T01:00:00Z",
    )

    assert audit.classify([failing]).state == audit.FAILING
    outcome = audit.classify([recovered, failing])
    assert outcome.state == audit.RECOVERED
    assert outcome.is_covered


def test_timeout_and_startup_failure_are_terminal_negative_verdicts() -> None:
    for conclusion in ("timed_out", "startup_failure"):
        assert audit.classify([attempt(conclusion)]).state == audit.FAILING


def test_undated_verdict_is_unverifiable_instead_of_inventing_order() -> None:
    assert audit.classify([attempt(started_at="")]).state == audit.UNVERIFIABLE


def test_gate_attempts_rejects_saturated_or_malformed_run_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        returncode = 0
        stdout = json.dumps([attempt() for _ in range(audit.RUN_FETCH_LIMIT)])

    monkeypatch.setattr(audit, "_run", lambda _argv: Completed())
    assert audit.gate_attempts("a" * 40, "sgajbi/lotus-core") is None

    Completed.stdout = json.dumps(["not-a-run"])
    assert audit.gate_attempts("a" * 40, "sgajbi/lotus-core") is None


def test_report_writer_creates_a_stable_machine_readable_artifact(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "audit.json"
    report = {"schema_version": "lotus.main-gate-coverage.v1", "revisions": []}

    audit._write_report(output, report)

    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_cli_reports_exact_duplicate_and_non_verdict_run_ids_and_missing_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_sha = "a" * 40
    second_sha = "b" * 40
    output = tmp_path / "audit.json"

    def fake_git(*args: str) -> list[str]:
        if args[:2] == ("rev-parse", "--verify"):
            return ["0" * 40]
        if args == ("rev-parse", "origin/main"):
            return [second_sha]
        return [f"{first_sha}\taaaaaaa\tfirst", f"{second_sha}\tbbbbbbb\tsecond"]

    def fake_attempts(sha: str, _repository: str) -> list[dict[str, object]]:
        if sha == second_sha:
            return []
        return [
            attempt(run_id=41),
            attempt("cancelled", run_id=42, started_at="2026-09-09T01:00:00Z"),
        ]

    monkeypatch.setattr(audit.shutil, "which", lambda _name: "gh")
    monkeypatch.setattr(audit, "_repository", lambda: "sgajbi/lotus-core")
    monkeypatch.setattr(audit, "_git", fake_git)
    monkeypatch.setattr(audit, "gate_attempts", fake_attempts)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_main_gate_coverage.py",
            "--baseline-ref",
            "refs/tags/baseline",
            "--output",
            str(output),
            "--fail-on-gap",
        ],
    )

    assert audit.main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["needs_recovery"] == [second_sha]
    assert report["revisions"][0]["duplicate_run_ids"] == [41, 42]
    assert report["revisions"][0]["non_verdict_run_ids"] == [42]
    assert report["revisions"][1]["run_ids"] == []


def test_cli_fails_closed_when_the_post_baseline_window_is_empty_or_truncated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(audit.shutil, "which", lambda _name: "gh")
    monkeypatch.setattr(audit, "_repository", lambda: "sgajbi/lotus-core")
    monkeypatch.setattr(audit, "gate_attempts", lambda _sha, _repository: [attempt()])

    for entries, limit in (
        ([], 400),
        ([f"{'a' * 40}\taaaaaaa\tone", f"{'b' * 40}\tbbbbbbb\ttwo"], 1),
    ):
        calls = iter([["0" * 40], ["f" * 40], [], entries])
        monkeypatch.setattr(audit, "_git", lambda *_args: next(calls))
        output = tmp_path / f"audit-{limit}-{len(entries)}.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "audit_main_gate_coverage.py",
                "--baseline-ref",
                "refs/tags/baseline",
                "--limit",
                str(limit),
                "--output",
                str(output),
                "--fail-on-gap",
            ],
        )

        assert audit.main() == 1
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["truncated"] is (len(entries) > limit)


def test_cli_fails_closed_when_the_versioned_baseline_cannot_be_resolved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit.json"
    monkeypatch.setattr(audit.shutil, "which", lambda _name: "gh")
    monkeypatch.setattr(audit, "_repository", lambda: "sgajbi/lotus-core")
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *_args: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "git")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_main_gate_coverage.py",
            "--baseline-ref",
            "refs/tags/missing",
            "--output",
            str(output),
            "--fail-on-gap",
        ],
    )

    assert audit.main() == 1
    assert json.loads(output.read_text(encoding="utf-8"))["fatal"] == (
        "baseline or origin/main could not be resolved"
    )
