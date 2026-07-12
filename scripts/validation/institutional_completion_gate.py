"""Run the governed RFC-086 institutional completion gate.

This wrapper runs the bank-day load scenario and then performs exhaustive
reconciliation against the exact generated run so main releasability always
produces the approval-grade completion artifacts consumed by the institutional
sign-off pack.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality.ci_service_sets import (  # noqa: E402
    INSTITUTIONAL_COMPLETION_GATE_SERVICES,
)
from tests.test_support.managed_compose_run import (  # noqa: E402
    prepare_managed_compose_run,
)

DEFAULT_OUTPUT_DIR = "output/task-runs"
DEFAULT_COMPOSE_FILE = "docker-compose.yml"
JSON_REPORT_PREFIX: Final[str] = "Wrote JSON report:"


@dataclass(frozen=True, slots=True)
class ScenarioArtifactMetadata:
    run_id: str
    business_date: str
    portfolio_count: int
    transactions_per_portfolio: int
    artifact_path: Path


def _run(cmd: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def _run_python_script(
    *,
    repo_root: Path,
    script_relative_path: str,
    args: list[str],
    environment: dict[str, str] | None = None,
) -> str:
    cmd = [sys.executable, script_relative_path, *args]
    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed.stdout


def _reported_scenario_artifact_path(*, stdout: str, repo_root: Path) -> Path | None:
    for line in reversed(stdout.splitlines()):
        normalized = line.strip()
        if not normalized.startswith(JSON_REPORT_PREFIX):
            continue
        reported_path = normalized.removeprefix(JSON_REPORT_PREFIX).strip()
        artifact_path = Path(reported_path)
        if not artifact_path.is_absolute():
            artifact_path = repo_root / artifact_path
        return artifact_path
    return None


def _latest_new_scenario_artifact(*, output_dir: Path, known_paths: set[Path]) -> Path:
    matches = sorted(
        (path for path in output_dir.glob("*-bank-day-load.json") if path not in known_paths),
        key=lambda path: path.stat().st_mtime,
    )
    if not matches:
        raise RuntimeError("Bank-day load scenario did not produce a new JSON artifact.")
    return matches[-1]


def _load_scenario_metadata(path: Path) -> ScenarioArtifactMetadata:
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = payload.get("config", {})
    run_id = str(payload.get("run_id") or "").strip()
    business_date = str(config.get("trade_date") or "").strip()
    portfolio_count = int(config.get("portfolio_count", 0) or 0)
    transactions_per_portfolio = int(config.get("transactions_per_portfolio", 0) or 0)
    if not run_id:
        raise ValueError(f"Scenario artifact {path} is missing run_id.")
    if not business_date:
        raise ValueError(f"Scenario artifact {path} is missing config.trade_date.")
    if portfolio_count <= 0:
        raise ValueError(f"Scenario artifact {path} has invalid portfolio_count={portfolio_count}.")
    if transactions_per_portfolio <= 0:
        raise ValueError(
            "Scenario artifact "
            f"{path} has invalid transactions_per_portfolio={transactions_per_portfolio}."
        )
    return ScenarioArtifactMetadata(
        run_id=run_id,
        business_date=business_date,
        portfolio_count=portfolio_count,
        transactions_per_portfolio=transactions_per_portfolio,
        artifact_path=path,
    )


def _scenario_args(parsed_args: argparse.Namespace) -> list[str]:
    return [
        "--portfolio-count",
        str(parsed_args.portfolio_count),
        "--transactions-per-portfolio",
        str(parsed_args.transactions_per_portfolio),
        "--transaction-batch-size",
        str(parsed_args.transaction_batch_size),
        "--sample-size",
        str(parsed_args.sample_size),
        "--drain-timeout-seconds",
        str(parsed_args.drain_timeout_seconds),
        "--output-dir",
        parsed_args.output_dir,
        "--trade-date",
        parsed_args.trade_date,
    ]


def _reconciliation_args(
    *,
    parsed_args: argparse.Namespace,
    scenario: ScenarioArtifactMetadata,
) -> list[str]:
    return [
        "--run-id",
        scenario.run_id,
        "--business-date",
        scenario.business_date,
        "--transactions-per-portfolio",
        str(scenario.transactions_per_portfolio),
        "--portfolio-limit",
        str(scenario.portfolio_count),
        "--output-dir",
        parsed_args.output_dir,
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio-count", type=int, default=1000)
    parser.add_argument("--transactions-per-portfolio", type=int, default=100)
    parser.add_argument("--transaction-batch-size", type=int, default=2000)
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--drain-timeout-seconds", type=int, default=7200)
    parser.add_argument("--trade-date", default="2026-04-17")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--compose-file", default=DEFAULT_COMPOSE_FILE)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--keep-compose", action="store_true")
    parser.add_argument(
        "--compose-log-path",
        default="output/task-runs/diagnostics/institutional-completion-compose.log",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    known_paths = set(output_dir.glob("*-bank-day-load.json"))

    scenario: ScenarioArtifactMetadata | None = None
    managed_run = prepare_managed_compose_run(
        scope="institutional-completion",
        compose_file=repo_root / args.compose_file,
        services=tuple(INSTITUTIONAL_COMPLETION_GATE_SERVICES),
        build=args.build,
        log_path=repo_root / args.compose_log_path,
        keep_stack=args.keep_compose,
        endpoint_urls={
            key: os.getenv(key)
            for key in (
                "E2E_INGESTION_URL",
                "E2E_QUERY_URL",
                "E2E_EVENT_REPLAY_URL",
                "E2E_TRANSACTION_PROCESSING_URL",
                "HOST_DATABASE_URL",
            )
        },
    )
    with managed_run:
        scenario_stdout = _run_python_script(
            repo_root=repo_root,
            script_relative_path="scripts/operations/bank_day_load_scenario.py",
            args=_scenario_args(args),
            environment=managed_run.runtime.values,
        )
        scenario_artifact = _reported_scenario_artifact_path(
            stdout=scenario_stdout,
            repo_root=repo_root,
        )
        if scenario_artifact is None:
            scenario_artifact = _latest_new_scenario_artifact(
                output_dir=output_dir,
                known_paths=known_paths,
            )
        scenario = _load_scenario_metadata(scenario_artifact)
        _run_python_script(
            repo_root=repo_root,
            script_relative_path="scripts/operations/bank_day_load_reconciliation_report.py",
            args=_reconciliation_args(parsed_args=args, scenario=scenario),
            environment=managed_run.runtime.values,
        )
    if scenario is None:
        raise RuntimeError("Institutional completion gate completed without scenario metadata.")
    print(scenario.artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
