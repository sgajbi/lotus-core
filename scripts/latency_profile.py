"""Endpoint latency profiler and CI gate for lotus-core.

This script runs a deterministic request set against ingestion/query endpoints,
computes latency statistics, writes JSON/Markdown artifacts, and optionally
fails the run when p95 exceeds endpoint-specific thresholds.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import requests

try:
    from scripts.ci_service_sets import LATENCY_GATE_SERVICES
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from ci_service_sets import LATENCY_GATE_SERVICES


@dataclass(frozen=True)
class EndpointCase:
    name: str
    method: str
    url: str
    payload: dict[str, Any] | None
    p95_budget_ms: float
    timeout_seconds: float = 30.0


def _percentile_ms(samples: list[float], percentile: int) -> float:
    if not samples:
        return 0.0
    if len(samples) == 1:
        return samples[0]
    index = max(0, min(percentile - 1, 99))
    return statistics.quantiles(samples, n=100)[index]


def _wait_ready(
    base_ingestion_url: str,
    base_event_replay_url: str,
    base_query_url: str,
    base_query_control_plane_url: str,
    timeout_seconds: int,
) -> None:
    deadline = time.time() + timeout_seconds
    session = requests.Session()
    while time.time() < deadline:
        try:
            ing = session.get(f"{base_ingestion_url}/health/ready", timeout=5)
            replay = session.get(f"{base_event_replay_url}/health/ready", timeout=5)
            qry = session.get(f"{base_query_url}/health/ready", timeout=5)
            ctrl = session.get(f"{base_query_control_plane_url}/health/ready", timeout=5)
            if (
                ing.status_code == 200
                and replay.status_code == 200
                and qry.status_code == 200
                and ctrl.status_code == 200
            ):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError("Services were not ready before timeout.")


def _run_compose_up(build: bool) -> None:
    cmd = ["docker", "compose", "up", "-d"]
    if build:
        cmd.append("--build")
    cmd.extend(LATENCY_GATE_SERVICES)
    subprocess.run(cmd, check=True)


def _raise_if_compose_service_failed(
    service_name: str,
) -> None:
    ps = subprocess.run(
        ["docker", "compose", "ps", "-a", "-q", service_name],
        check=False,
        capture_output=True,
        text=True,
    )
    container_id = ps.stdout.strip()
    if not container_id:
        return

    inspect = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.State.Status}}|{{.State.ExitCode}}",
            container_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    status, _, exit_code = inspect.stdout.strip().partition("|")
    if status == "exited" and exit_code != "0":
        raise RuntimeError(
            "Compose service "
            f"'{service_name}' exited with status {exit_code} "
            "before latency profiling."
        )


def _pick_identifier_from_payload(payload: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for value in payload.values():
            picked = _pick_identifier_from_payload(value, keys)
            if picked:
                return picked
    if isinstance(payload, list):
        for item in payload:
            picked = _pick_identifier_from_payload(item, keys)
            if picked:
                return picked
    return None


def _resolve_runtime_ids(
    session: requests.Session,
    *,
    query_base_url: str,
    query_control_plane_base_url: str,
    portfolio_id: str,
    benchmark_id: str,
    timeout_seconds: int,
    progress_check: Callable[[], None] | None = None,
) -> tuple[str, str]:
    resolved_portfolio_id = portfolio_id
    resolved_benchmark_id = benchmark_id

    def _portfolio_ready(candidate_id: str) -> bool:
        get_urls = [
            f"{query_base_url}/portfolios/{candidate_id}/positions",
            f"{query_base_url}/portfolios/{candidate_id}/transactions?limit=1",
            f"{query_control_plane_base_url}/support/portfolios/{candidate_id}/overview",
        ]
        post_checks = [
            (
                f"{query_control_plane_base_url}/integration/portfolios/{candidate_id}/analytics/portfolio-timeseries",
                {
                    "as_of_date": "2026-03-01",
                    "period": "three_months",
                    "frequency": "daily",
                    "consumer_system": "lotus-performance",
                    "page": {"page_size": 100},
                },
            ),
            (
                f"{query_control_plane_base_url}/integration/portfolios/{candidate_id}/analytics/position-timeseries",
                {
                    "as_of_date": "2026-03-01",
                    "period": "three_months",
                    "frequency": "daily",
                    "consumer_system": "lotus-performance",
                    "page": {"page_size": 100},
                },
            ),
        ]
        for url in get_urls:
            try:
                response = session.get(url, timeout=10)
            except requests.RequestException:
                return False
            if not (200 <= response.status_code < 300):
                return False
        for url, payload in post_checks:
            try:
                response = session.post(url, json=payload, timeout=15)
            except requests.RequestException:
                return False
            if not (200 <= response.status_code < 300):
                return False
        return True

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if progress_check is not None:
            progress_check()
        candidate_ids: list[str] = [portfolio_id]
        try:
            response = session.get(f"{query_base_url}/lookups/portfolios?limit=50", timeout=10)
            if response.status_code == 200:
                payload = response.json()
                discovered: list[str] = []

                def _collect_ids(node: Any) -> None:
                    if isinstance(node, dict):
                        for key in ("portfolio_id", "id", "portfolioId"):
                            value = node.get(key)
                            if isinstance(value, str) and value.strip():
                                discovered.append(value)
                        for value in node.values():
                            _collect_ids(value)
                    elif isinstance(node, list):
                        for item in node:
                            _collect_ids(item)

                _collect_ids(payload)
                candidate_ids = []
                for discovered_id in discovered:
                    if discovered_id not in candidate_ids:
                        candidate_ids.append(discovered_id)
                if portfolio_id not in candidate_ids:
                    candidate_ids.append(portfolio_id)
        except requests.RequestException:
            pass

        for candidate_id in candidate_ids:
            if _portfolio_ready(candidate_id):
                resolved_portfolio_id = candidate_id
                break
        if resolved_portfolio_id != portfolio_id:
            break
        time.sleep(2)

    if resolved_portfolio_id != portfolio_id:
        print(
            f"Latency profile portfolio_id override: '{portfolio_id}' -> '{resolved_portfolio_id}'"
        )

    try:
        response = session.post(
            f"{query_control_plane_base_url}/integration/benchmarks/catalog",
            json={"as_of_date": "2026-03-01"},
            timeout=15,
        )
        if response.status_code == 200:
            candidate = _pick_identifier_from_payload(
                response.json(),
                ("benchmark_id", "id", "benchmarkId"),
            )
            if candidate and candidate != benchmark_id:
                print(f"Latency profile benchmark_id override: '{benchmark_id}' -> '{candidate}'")
                resolved_benchmark_id = candidate
    except requests.RequestException:
        pass

    return resolved_portfolio_id, resolved_benchmark_id


def _cases(
    ingestion_base_url: str,
    event_replay_base_url: str,
    query_base_url: str,
    query_control_plane_base_url: str,
    portfolio_id: str,
    benchmark_id: str,
    include_protected_ops: bool,
) -> list[EndpointCase]:
    baseline = [
        EndpointCase("ing_ready", "GET", f"{ingestion_base_url}/health/ready", None, 300),
        EndpointCase("qry_ready", "GET", f"{query_base_url}/health/ready", None, 240),
        EndpointCase(
            "lookups_portfolios",
            "GET",
            f"{query_base_url}/lookups/portfolios?limit=50",
            None,
            180,
        ),
        EndpointCase(
            "portfolio_positions",
            "GET",
            f"{query_base_url}/portfolios/{portfolio_id}/positions",
            None,
            280,
        ),
        EndpointCase(
            "portfolio_transactions",
            "GET",
            f"{query_base_url}/portfolios/{portfolio_id}/transactions?limit=50",
            None,
            280,
        ),
        EndpointCase(
            "support_overview",
            "GET",
            f"{query_control_plane_base_url}/support/portfolios/{portfolio_id}/overview",
            None,
            240,
        ),
        EndpointCase(
            "benchmark_catalog",
            "POST",
            f"{query_control_plane_base_url}/integration/benchmarks/catalog",
            {"as_of_date": "2026-03-01"},
            320,
        ),
        EndpointCase(
            "index_catalog",
            "POST",
            f"{query_control_plane_base_url}/integration/indices/catalog",
            {"as_of_date": "2026-03-01"},
            320,
        ),
        EndpointCase(
            "benchmark_market_series",
            "POST",
            f"{query_control_plane_base_url}/integration/benchmarks/{benchmark_id}/market-series",
            {
                "as_of_date": "2026-03-01",
                "window": {"start_date": "2025-12-01", "end_date": "2026-03-01"},
                "frequency": "daily",
                "include_components": True,
                "series_fields": [
                    "index_price",
                    "index_return",
                    "benchmark_return",
                    "component_weight",
                ],
            },
            420,
            timeout_seconds=45.0,
        ),
        EndpointCase(
            "analytics_portfolio_timeseries",
            "POST",
            f"{query_control_plane_base_url}/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
            {
                "as_of_date": "2026-03-01",
                "period": "one_year",
                "frequency": "daily",
                "consumer_system": "lotus-performance",
                "page": {"page_size": 500},
            },
            420,
            timeout_seconds=45.0,
        ),
        EndpointCase(
            "analytics_position_timeseries",
            "POST",
            f"{query_control_plane_base_url}/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
            {
                "as_of_date": "2026-03-01",
                "period": "three_months",
                "frequency": "daily",
                "consumer_system": "lotus-performance",
                "page": {"page_size": 500},
            },
            420,
            timeout_seconds=45.0,
        ),
    ]
    if include_protected_ops:
        baseline.extend(
            [
                EndpointCase(
                    "ingestion_health_summary",
                    "GET",
                    f"{event_replay_base_url}/ingestion/health/summary",
                    None,
                    300,
                ),
                EndpointCase(
                    "ingestion_jobs_list",
                    "GET",
                    f"{event_replay_base_url}/ingestion/jobs?limit=20",
                    None,
                    300,
                ),
            ]
        )
    return baseline


def _call_case(session: requests.Session, case: EndpointCase) -> requests.Response:
    if case.method == "GET":
        return session.get(case.url, timeout=case.timeout_seconds)
    return session.post(case.url, json=case.payload, timeout=case.timeout_seconds)


def run_profile(
    *,
    ingestion_base_url: str,
    event_replay_base_url: str,
    query_base_url: str,
    query_control_plane_base_url: str,
    portfolio_id: str,
    benchmark_id: str,
    include_protected_ops: bool,
    warmup_runs: int,
    measured_runs: int,
) -> list[dict[str, Any]]:
    session = requests.Session()
    results: list[dict[str, Any]] = []

    for case in _cases(
        ingestion_base_url,
        event_replay_base_url,
        query_base_url,
        query_control_plane_base_url,
        portfolio_id,
        benchmark_id,
        include_protected_ops,
    ):
        for _ in range(warmup_runs):
            try:
                _call_case(session, case)
            except requests.RequestException:
                pass

        samples: list[float] = []
        statuses: list[int] = []
        errors: list[str] = []
        for _ in range(measured_runs):
            start = time.perf_counter()
            try:
                response = _call_case(session, case)
                elapsed = (time.perf_counter() - start) * 1000
                samples.append(elapsed)
                statuses.append(response.status_code)
            except requests.RequestException as exc:
                elapsed = (time.perf_counter() - start) * 1000
                samples.append(elapsed)
                statuses.append(-1)
                errors.append(str(exc))

        ok_runs = sum(1 for status in statuses if 200 <= status < 300)
        p50 = _percentile_ms(samples, 50)
        p95 = _percentile_ms(samples, 95)
        p99 = _percentile_ms(samples, 99)
        results.append(
            {
                "name": case.name,
                "method": case.method,
                "url": case.url,
                "runs": measured_runs,
                "ok_runs": ok_runs,
                "status_set": sorted(set(statuses)),
                "avg_ms": round(sum(samples) / len(samples), 2) if samples else 0.0,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
                "max_ms": round(max(samples), 2) if samples else 0.0,
                "min_ms": round(min(samples), 2) if samples else 0.0,
                "p95_budget_ms": case.p95_budget_ms,
                "errors": errors[:3],
            }
        )
    return results


def _write_artifacts(
    *,
    results: list[dict[str, Any]],
    output_dir: Path,
    run_id: str,
) -> tuple[Path, Path]:
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}-latency-profile.json"
    md_path = output_dir / f"{run_id}-latency-profile.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Endpoint Latency Profile",
        f"- Run ID: {run_id}",
        "",
        "| Endpoint | OK/Total | Avg ms | P50 | P95 | Budget | P99 | Statuses |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in sorted(results, key=lambda item: item["p95_ms"], reverse=True):
        statuses = ",".join(str(status) for status in result["status_set"])
        lines.append(
            (
                "| {name} | {ok}/{runs} | {avg} | {p50} | {p95} | {budget} | {p99} | {statuses} |"
            ).format(
                name=result["name"],
                ok=result["ok_runs"],
                runs=result["runs"],
                avg=result["avg_ms"],
                p50=result["p50_ms"],
                p95=result["p95_ms"],
                budget=result["p95_budget_ms"],
                p99=result["p99_ms"],
                statuses=statuses,
            )
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def _enforce_gate(results: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    violations: list[str] = []
    for result in results:
        if result["ok_runs"] != result["runs"]:
            violations.append(
                f"{result['name']}: non-2xx responses observed "
                f"({result['ok_runs']}/{result['runs']})"
            )
        if result["p95_ms"] > result["p95_budget_ms"]:
            violations.append(
                f"{result['name']}: p95 {result['p95_ms']}ms exceeds budget "
                f"{result['p95_budget_ms']}ms"
            )
    return (len(violations) == 0, violations)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lotus-core endpoint latency profiling.")
    parser.add_argument(
        "--ingestion-base-url", default=os.getenv("E2E_INGESTION_URL", "http://localhost:8200")
    )
    parser.add_argument(
        "--query-base-url", default=os.getenv("E2E_QUERY_URL", "http://localhost:8201")
    )
    parser.add_argument(
        "--event-replay-base-url",
        default=os.getenv("E2E_EVENT_REPLAY_URL", "http://localhost:8209"),
    )
    parser.add_argument(
        "--query-control-plane-base-url",
        default=os.getenv("E2E_QUERY_CONTROL_PLANE_URL", "http://localhost:8202"),
    )
    parser.add_argument("--portfolio-id", default="DEMO_DPM_EUR_001")
    parser.add_argument("--benchmark-id", default="BMK_GLOBAL_BALANCED_60_40")
    parser.add_argument("--warmup-runs", type=int, default=5)
    parser.add_argument("--measured-runs", type=int, default=30)
    parser.add_argument("--ready-timeout-seconds", type=int, default=180)
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument(
        "--include-protected-ops",
        action="store_true",
        help="Include protected ingestion operational endpoints in the latency suite.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    if not args.skip_compose:
        _run_compose_up(build=args.build)

    _wait_ready(
        base_ingestion_url=args.ingestion_base_url,
        base_event_replay_url=args.event_replay_base_url,
        base_query_url=args.query_base_url,
        base_query_control_plane_url=args.query_control_plane_base_url,
        timeout_seconds=args.ready_timeout_seconds,
    )

    session = requests.Session()
    resolved_portfolio_id, resolved_benchmark_id = _resolve_runtime_ids(
        session,
        query_base_url=args.query_base_url,
        query_control_plane_base_url=args.query_control_plane_base_url,
        portfolio_id=args.portfolio_id,
        benchmark_id=args.benchmark_id,
        timeout_seconds=args.ready_timeout_seconds,
        progress_check=(
            None
            if args.skip_compose
            else lambda: _raise_if_compose_service_failed("demo_data_loader")
        ),
    )

    results = run_profile(
        ingestion_base_url=args.ingestion_base_url,
        event_replay_base_url=args.event_replay_base_url,
        query_base_url=args.query_base_url,
        query_control_plane_base_url=args.query_control_plane_base_url,
        portfolio_id=resolved_portfolio_id,
        benchmark_id=resolved_benchmark_id,
        include_protected_ops=args.include_protected_ops,
        warmup_runs=args.warmup_runs,
        measured_runs=args.measured_runs,
    )

    json_path, md_path = _write_artifacts(
        results=results,
        output_dir=Path(args.output_dir),
        run_id=run_id,
    )
    print(f"Wrote: {json_path.resolve()}")
    print(f"Wrote: {md_path.resolve()}")

    top = sorted(results, key=lambda item: item["p95_ms"], reverse=True)[:5]
    for result in top:
        print(
            f"TOP {result['name']} p95={result['p95_ms']}ms budget={result['p95_budget_ms']}ms "
            f"ok={result['ok_runs']}/{result['runs']}"
        )

    if args.enforce:
        passed, violations = _enforce_gate(results)
        if not passed:
            for violation in violations:
                print(f"GATE FAIL: {violation}")
            return 1
        print("Latency gate passed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
