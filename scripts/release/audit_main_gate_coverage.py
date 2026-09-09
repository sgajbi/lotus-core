"""Audit verdict-bearing Main Releasability evidence after enforcement began."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WORKFLOW = "main-releasability.yml"
VERDICTS = frozenset({"success", "failure", "timed_out", "startup_failure"})
FAILURES = VERDICTS - {"success"}
PENDING_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})
RUN_FETCH_LIMIT = 100

UNGATED = "ungated"
UNVERIFIABLE = "unverifiable"
PASSING = "passing"
RECOVERED = "recovered"
FAILING = "failing"


@dataclass(frozen=True)
class CommitOutcome:
    state: str
    detail: str = ""

    @property
    def is_covered(self) -> bool:
        return self.state in {PASSING, RECOVERED, FAILING}


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True)


def _git(*args: str) -> list[str]:
    completed = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _record(payload: dict[str, Any], *, attempt: int | None = None) -> dict[str, Any]:
    run_id = payload.get("databaseId") or payload.get("id")
    return {
        "run_id": int(run_id) if run_id is not None else None,
        "attempt": int(attempt if attempt is not None else payload.get("attempt") or 1),
        "status": str(payload.get("status") or ""),
        "conclusion": str(payload.get("conclusion") or ""),
        "started_at": str(payload.get("startedAt") or payload.get("run_started_at") or ""),
        "url": str(payload.get("url") or ""),
    }


def _earlier_attempt(repository: str, run_id: int, attempt: int) -> dict[str, Any] | None:
    completed = _run(
        [
            "gh",
            "api",
            f"repos/{repository}/actions/runs/{run_id}/attempts/{attempt}",
        ]
    )
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            return None
        payload["id"] = run_id
        return _record(payload, attempt=attempt)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def gate_attempts(sha: str, repository: str) -> list[dict[str, Any]] | None:
    completed = _run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repository,
            "--workflow",
            WORKFLOW,
            "--commit",
            sha,
            "--limit",
            str(RUN_FETCH_LIMIT),
            "--json",
            "conclusion,status,startedAt,databaseId,attempt,url",
        ]
    )
    if completed.returncode != 0:
        return None
    try:
        runs = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(runs, list) or len(runs) >= RUN_FETCH_LIMIT:
        return None

    attempts: list[dict[str, Any]] = []
    try:
        for run in runs:
            if not isinstance(run, dict):
                return None
            newest = int(run.get("attempt") or 1)
            current = _record(run)
            run_id = current["run_id"]
            if run_id is None:
                return None
            attempts.append(current)
            for superseded in range(1, newest):
                earlier = _earlier_attempt(repository, run_id, superseded)
                if earlier is None:
                    return None
                attempts.append(earlier)
    except (TypeError, ValueError):
        return None
    return attempts


def classify(attempts: list[dict[str, Any]] | None) -> CommitOutcome:
    if attempts is None:
        return CommitOutcome(UNVERIFIABLE, "run history could not be read in full")
    undated = [
        attempt
        for attempt in attempts
        if attempt["conclusion"] in VERDICTS and not attempt["started_at"]
    ]
    if undated:
        return CommitOutcome(UNVERIFIABLE, "a verdict-bearing attempt has no start time")
    ordered = sorted(
        attempts,
        key=lambda item: (item["started_at"], item["run_id"] or 0, item["attempt"]),
    )
    verdicts = [item["conclusion"] for item in ordered if item["conclusion"] in VERDICTS]
    if verdicts:
        failures = [verdict for verdict in verdicts if verdict in FAILURES]
        if verdicts[-1] == "success":
            if failures:
                return CommitOutcome(RECOVERED, f"{len(failures)} earlier failing verdict(s)")
            return CommitOutcome(PASSING)
        return CommitOutcome(FAILING, f"newest verdict is {verdicts[-1]}")
    if not ordered:
        return CommitOutcome(UNGATED, "no workflow run exists")
    pending = sorted({item["status"] for item in ordered if item["status"] in PENDING_STATUSES})
    if pending:
        return CommitOutcome(UNVERIFIABLE, f"nonterminal run status: {', '.join(pending)}")
    conclusions = sorted({item["conclusion"] or item["status"] for item in ordered})
    return CommitOutcome(UNVERIFIABLE, f"runs exist without a verdict: {conclusions}")


def _repository() -> str | None:
    completed = _run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    return completed.stdout.strip() if completed.returncode == 0 else None


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-gap", action="store_true")
    return parser.parse_args()


def _initial_report(baseline_ref: str) -> dict[str, Any]:
    return {
        "schema_version": "lotus.main-gate-coverage.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow": WORKFLOW,
        "baseline_ref": baseline_ref,
        "revisions": [],
    }


def _fatal(report: dict[str, Any], output: Path | None, message: str, *, fail_on_gap: bool) -> int:
    report["fatal"] = message
    _write_report(output, report)
    print(message)
    return 1 if fail_on_gap else 0


def _resolve_window(baseline_ref: str, limit: int) -> tuple[str, str, list[str], bool]:
    baseline_sha = _git("rev-parse", "--verify", f"{baseline_ref}^{{commit}}")[0]
    main_sha = _git("rev-parse", "origin/main")[0]
    _git("merge-base", "--is-ancestor", baseline_sha, main_sha)
    entries = _git(
        "log",
        "--reverse",
        "--format=%H%x09%h%x09%s",
        f"{baseline_sha}..{main_sha}",
    )
    return baseline_sha, main_sha, entries[:limit], len(entries) > limit


def _revision_record(entry: str, repository: str) -> tuple[dict[str, Any], CommitOutcome]:
    sha, short, subject = entry.split("\t", 2)
    attempts = gate_attempts(sha, repository)
    outcome = classify(attempts)
    run_ids = sorted({item["run_id"] for item in attempts or [] if item["run_id"] is not None})
    non_verdict_run_ids = sorted(
        {
            item["run_id"]
            for item in attempts or []
            if item["run_id"] is not None and item["conclusion"] not in VERDICTS
        }
    )
    record = {
        "revision_sha": sha,
        "subject": subject,
        "state": outcome.state,
        "detail": outcome.detail,
        "run_ids": run_ids,
        "duplicate_run_ids": run_ids if len(run_ids) > 1 else [],
        "non_verdict_run_ids": non_verdict_run_ids,
        "attempts": attempts,
    }
    if outcome.state != PASSING or record["duplicate_run_ids"] or non_verdict_run_ids:
        print(
            f"{outcome.state.upper():12} {short} runs={run_ids or 'none'} "
            f"duplicates={record['duplicate_run_ids'] or 'none'} "
            f"non_verdict={non_verdict_run_ids or 'none'} {outcome.detail}"
        )
    return record, outcome


def _audit(entries: list[str], repository: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {state: 0 for state in (UNGATED, UNVERIFIABLE, PASSING, RECOVERED, FAILING)}
    records: list[dict[str, Any]] = []
    for entry in entries:
        record, outcome = _revision_record(entry, repository)
        counts[outcome.state] += 1
        records.append(record)
    return records, counts


def _print_summary(counts: dict[str, int], audited_count: int, truncated: bool) -> None:
    print(
        f"audited {audited_count} post-baseline revision(s): "
        f"{counts[UNGATED]} ungated, {counts[UNVERIFIABLE]} unverifiable, "
        f"{counts[PASSING]} passing, {counts[RECOVERED]} recovered, "
        f"{counts[FAILING]} failing; truncated={truncated}"
    )


def main() -> int:
    arguments = _arguments()
    report = _initial_report(arguments.baseline_ref)
    if shutil.which("gh") is None:
        return _fatal(
            report,
            arguments.output,
            "gh is not available",
            fail_on_gap=arguments.fail_on_gap,
        )

    repository = _repository()
    if not repository:
        return _fatal(
            report,
            arguments.output,
            "repository identity could not be resolved",
            fail_on_gap=arguments.fail_on_gap,
        )
    report["repository"] = repository

    try:
        baseline_sha, main_sha, selected, truncated = _resolve_window(
            arguments.baseline_ref, arguments.limit
        )
    except (subprocess.CalledProcessError, IndexError):
        return _fatal(
            report,
            arguments.output,
            "baseline or origin/main could not be resolved",
            fail_on_gap=arguments.fail_on_gap,
        )

    report.update({"baseline_sha": baseline_sha, "main_sha": main_sha})
    records, counts = _audit(selected, repository)
    report["revisions"] = records

    report["counts"] = counts
    report["truncated"] = truncated
    report["audited_revision_count"] = len(selected)
    report["needs_recovery"] = [
        item["revision_sha"]
        for item in report["revisions"]
        if item["state"] in {UNGATED, UNVERIFIABLE}
    ]
    _write_report(arguments.output, report)

    _print_summary(counts, len(selected), truncated)
    if report["needs_recovery"]:
        print("recovery revisions: " + ", ".join(report["needs_recovery"]))
    if arguments.fail_on_gap and (report["needs_recovery"] or truncated or not selected):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
