"""Generate source-safe report-only PostgreSQL hot-path plan evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from scripts.operations.database_evidence.contract import (
    DatabaseEvidenceContractError,
    build_hot_path_evidence_artifact,
    load_hot_path_plan_fragments,
    load_hot_path_scenario_catalog,
    write_hot_path_evidence_artifact,
)
from scripts.operations.database_evidence.runtime_fragments import FRAGMENT_DIRECTORY_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "contracts/operations/database-hot-path-scenarios.v1.json"
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT / "output/database-hot-path-evidence/database-hot-path-evidence.json"
)


@dataclass(frozen=True, slots=True)
class DatabaseHotPathEvidencePlan:
    pytest_nodes: tuple[str, ...]


def build_evidence_plan() -> DatabaseHotPathEvidencePlan:
    """Return the exact deterministic PostgreSQL scenario execution order."""

    return DatabaseHotPathEvidencePlan(
        pytest_nodes=(
            "tests/integration/libs/portfolio-common/"
            "test_latest_position_query_plans.py::"
            "test_latest_snapshot_and_history_queries_use_covering_indexes",
            "tests/integration/scripts/operations/database_evidence/"
            "test_operations_support.py::"
            "test_operations_support_page_reports_bounded_plan_posture",
            "tests/integration/scripts/operations/database_evidence/"
            "test_reconciliation.py::"
            "test_reconciliation_control_scan_is_bounded_and_index_backed",
            "tests/integration/scripts/operations/database_evidence/"
            "test_transaction_ledger.py::"
            "test_transaction_ledger_page_and_count_are_bounded_and_index_backed",
            "tests/integration/scripts/operations/database_evidence/"
            "test_valuation_claim.py::"
            "test_valuation_claim_plan_is_bounded_indexed_and_rollback_safe",
        )
    )


def execute_evidence_tests(
    plan: DatabaseHotPathEvidencePlan,
    *,
    fragment_directory: Path,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    """Run only governed scenario nodes with an isolated fragment directory."""

    environment = os.environ.copy()
    environment[FRAGMENT_DIRECTORY_ENV] = str(fragment_directory.resolve())
    result = command_runner(
        [sys.executable, "-m", "pytest", "-q", *plan.pytest_nodes],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        text=True,
    )
    return int(result.returncode)


def resolve_clean_git_sha(
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Resolve exact source identity only when no uncommitted files can escape it."""

    status = command_runner(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise DatabaseEvidenceContractError("source_worktree_not_clean")
    revision = command_runner(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return revision.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_evidence_plan()
    if args.plan_only:
        print(json.dumps(asdict(plan), indent=2, sort_keys=True))
        return 0
    try:
        catalog = load_hot_path_scenario_catalog(CATALOG_PATH)
        git_sha = resolve_clean_git_sha()
        with tempfile.TemporaryDirectory(prefix="lotus-db-plan-evidence-") as raw_directory:
            fragment_directory = Path(raw_directory)
            return_code = execute_evidence_tests(
                plan,
                fragment_directory=fragment_directory,
            )
            if return_code != 0:
                return return_code
            results = load_hot_path_plan_fragments(fragment_directory, catalog=catalog)
        if resolve_clean_git_sha() != git_sha:
            raise DatabaseEvidenceContractError("source_revision_changed_during_evidence")
        artifact = build_hot_path_evidence_artifact(
            catalog=catalog,
            results=results,
            git_sha=git_sha,
            generated_at=datetime.now(timezone.utc),
        )
        write_hot_path_evidence_artifact(args.output, artifact)
    except (DatabaseEvidenceContractError, OSError, subprocess.SubprocessError) as exc:
        print(f"Database hot-path evidence failed closed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "content_hash": artifact["content_hash"],
                "evidence_posture": artifact["evidence_posture"],
                "scenario_count": len(results),
                "status": artifact["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
