"""Deterministic docker endpoint smoke runner for lotus-core.

This script boots (or reuses) the local docker stack, executes a deterministic
ingest->query flow with unique identifiers, and validates a fixed endpoint
status matrix for ingestion and query services.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


@dataclass(slots=True)
class CheckResult:
    name: str
    method: str
    url: str
    status: int
    ok: bool
    note: str
    response: Any


def _run(cmd: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        print(f"Command failed ({completed.returncode}): {' '.join(cmd)}", file=sys.stderr)
        if completed.stdout:
            print(completed.stdout, file=sys.stderr)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        raise RuntimeError("command failed")


def _compose_up_with_retry(*, compose_file: str, repo_root: Path, build: bool) -> None:
    up_cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
    if build:
        up_cmd.append("--build")

    attempts = 2
    for attempt in range(1, attempts + 1):
        try:
            _run(up_cmd, cwd=repo_root)
            return
        except RuntimeError:
            if attempt == attempts:
                raise
            # Handle transient Kafka/ZK startup races by recycling containers once.
            _run(["docker", "compose", "-f", compose_file, "down"], cwd=repo_root)
            time.sleep(5)


def _call(
    results: list[CheckResult],
    *,
    name: str,
    method: str,
    url: str,
    expected: set[int],
    **kwargs: Any,
) -> requests.Response | None:
    try:
        response = requests.request(method=method, url=url, timeout=40, **kwargs)
        content_type = response.headers.get("content-type", "")
        body: Any
        if "application/json" in content_type:
            try:
                body = response.json()
            except ValueError:
                body = response.text[:1000]
        else:
            body = response.text[:1000] if response.text else None
        ok = response.status_code in expected
        results.append(
            CheckResult(
                name=name,
                method=method,
                url=url,
                status=response.status_code,
                ok=ok,
                note="",
                response=body,
            )
        )
        return response
    except Exception as exc:  # pragma: no cover - defensive runtime capture
        results.append(
            CheckResult(
                name=name,
                method=method,
                url=url,
                status=0,
                ok=False,
                note=str(exc),
                response=None,
            )
        )
        return None


def _record_contract_check(
    results: list[CheckResult],
    *,
    name: str,
    url: str,
    ok: bool,
    note: str,
    response: Any,
) -> None:
    results.append(
        CheckResult(
            name=name,
            method="CONTRACT",
            url=url,
            status=200 if ok else 0,
            ok=ok,
            note=note,
            response=response,
        )
    )


def _response_json_or_none(response: requests.Response | None) -> Any:
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _wait_ready(base_url: str, timeout_seconds: int) -> None:
    ready_url = f"{base_url}/health/ready"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(ready_url, timeout=5)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for ready endpoint: {ready_url}")


def _wait_portfolio_visible(query_base_url: str, portfolio_id: str, timeout_seconds: int) -> None:
    url = f"{query_base_url}/portfolios/{portfolio_id}"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=8)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(
        f"Timed out waiting for portfolio to appear in query service: {portfolio_id}"
    )


def _write_report(
    *,
    output_dir: Path,
    run_id: str,
    summary: dict[str, Any],
    results: list[CheckResult],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        **summary,
        "results": [asdict(item) for item in results],
    }
    json_path = output_dir / f"{run_id}-docker-endpoint-smoke.json"
    md_path = output_dir / f"{run_id}-docker-endpoint-smoke.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    failures = [item for item in results if not item.ok]
    lines = [
        f"# Docker Endpoint Smoke {run_id}",
        "",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Portfolio: {summary['portfolio_id']}",
        f"- Security: {summary['security_id']}",
        f"- ISIN: {summary['isin']}",
        "",
    ]
    if failures:
        lines.append("## Failures")
        for failure in failures:
            lines.append(
                f"- {failure.name} `{failure.method} {failure.url}` -> "
                f"{failure.status} ({failure.note})"
            )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic lotus-core docker endpoint smoke."
    )
    parser.add_argument("--repo-root", default=".", help="Path to lotus-core repository root.")
    parser.add_argument(
        "--compose-file", default="docker-compose.yml", help="Docker compose file path."
    )
    parser.add_argument(
        "--ingestion-base-url", default=os.getenv("E2E_INGESTION_URL", "http://localhost:8200")
    )
    parser.add_argument(
        "--query-base-url", default=os.getenv("E2E_QUERY_URL", "http://localhost:8201")
    )
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument(
        "--reset-volumes", action="store_true", help="Run docker compose down -v first."
    )
    parser.add_argument("--build", action="store_true", help="Run compose up with --build.")
    parser.add_argument(
        "--skip-compose", action="store_true", help="Do not run docker compose commands."
    )
    parser.add_argument("--ready-timeout-seconds", type=int, default=180)
    parser.add_argument("--query-visible-timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    compose_file = str((repo_root / args.compose_file).resolve())

    if not args.skip_compose:
        if args.reset_volumes:
            _run(["docker", "compose", "-f", compose_file, "down", "-v"], cwd=repo_root)
        _compose_up_with_retry(compose_file=compose_file, repo_root=repo_root, build=args.build)

    _wait_ready(args.ingestion_base_url, args.ready_timeout_seconds)
    _wait_ready(args.query_base_url, args.ready_timeout_seconds)

    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    portfolio_id = f"PORT_SMOKE_{run_id}"
    security_id = f"SEC_SMOKE_{run_id}"
    instrument_id = f"INST_SMOKE_{run_id}"
    transaction_id = f"TX_SMOKE_{run_id}"
    transaction_id_2 = f"TX2_SMOKE_{run_id}"
    csv_transaction_id = f"TXUP_SMOKE_{run_id}"
    isin = f"US{run_id.replace('-', '')[-10:]}"
    now_utc = datetime.now(UTC).replace(microsecond=0)
    trade_timestamp = now_utc.isoformat().replace("+00:00", "Z")
    trade_date = trade_timestamp[:10]

    tmp_csv = repo_root / ".tmp_upload_tx.csv"
    with tmp_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "transaction_id",
                "portfolio_id",
                "instrument_id",
                "security_id",
                "transaction_date",
                "transaction_type",
                "quantity",
                "price",
                "gross_transaction_amount",
                "trade_currency",
                "currency",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "transaction_id": csv_transaction_id,
                "portfolio_id": portfolio_id,
                "instrument_id": instrument_id,
                "security_id": security_id,
                "transaction_date": trade_timestamp,
                "transaction_type": "BUY",
                "quantity": "1",
                "price": "10",
                "gross_transaction_amount": "10",
                "trade_currency": "USD",
                "currency": "USD",
            }
        )

    results: list[CheckResult] = []
    ingest = args.ingestion_base_url
    query = args.query_base_url
    ops_headers = {"X-Lotus-Ops-Token": "lotus-core-ops-local"}

    _call(results, name="ing live", method="GET", url=f"{ingest}/health/live", expected={200})
    _call(results, name="ing ready", method="GET", url=f"{ingest}/health/ready", expected={200})
    _call(results, name="ing metrics", method="GET", url=f"{ingest}/metrics", expected={200})
    _call(
        results,
        name="ops set normal",
        method="PUT",
        url=f"{ingest}/ingestion/ops/control",
        expected={200},
        headers=ops_headers,
        json={"mode": "normal", "updated_by": "deterministic_smoke"},
    )

    _call(
        results,
        name="ingest business dates",
        method="POST",
        url=f"{ingest}/ingest/business-dates",
        expected={202},
        json={"business_dates": [{"business_date": trade_date}]},
    )
    _call(
        results,
        name="ingest fx rates",
        method="POST",
        url=f"{ingest}/ingest/fx-rates",
        expected={202},
        json={
            "fx_rates": [
                {
                    "from_currency": "USD",
                    "to_currency": "CHF",
                    "rate": 0.9,
                    "rate_date": trade_date,
                }
            ]
        },
    )
    _call(
        results,
        name="ingest instruments",
        method="POST",
        url=f"{ingest}/ingest/instruments",
        expected={202},
        json={
            "instruments": [
                {
                    "security_id": security_id,
                    "isin": isin,
                    "name": "Smoke Asset",
                    "currency": "USD",
                    "product_type": "Equity",
                    "asset_class": "Equity",
                }
            ]
        },
    )
    _call(
        results,
        name="ingest portfolios",
        method="POST",
        url=f"{ingest}/ingest/portfolios",
        expected={202},
        json={
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2024-01-01",
                    "risk_exposure": "Medium",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Discretionary",
                    "booking_center_code": "SGP",
                    "client_id": "CLIENT_SMOKE_001",
                    "status": "Active",
                }
            ]
        },
    )
    _call(
        results,
        name="ingest market prices",
        method="POST",
        url=f"{ingest}/ingest/market-prices",
        expected={202},
        json={
            "market_prices": [
                {
                    "security_id": security_id,
                    "price": 180.25,
                    "currency": "USD",
                    "price_date": trade_date,
                }
            ]
        },
    )
    _call(
        results,
        name="ingest transaction",
        method="POST",
        url=f"{ingest}/ingest/transaction",
        expected={202},
        json={
            "transaction_id": transaction_id,
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
            "security_id": security_id,
            "transaction_date": trade_timestamp,
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 180.25,
            "gross_transaction_amount": 1802.5,
            "trade_currency": "USD",
            "currency": "USD",
        },
    )
    _call(
        results,
        name="ingest transactions",
        method="POST",
        url=f"{ingest}/ingest/transactions",
        expected={202},
        json={
            "transactions": [
                {
                    "transaction_id": transaction_id_2,
                    "portfolio_id": portfolio_id,
                    "instrument_id": instrument_id,
                    "security_id": security_id,
                    "transaction_date": trade_timestamp,
                    "transaction_type": "BUY",
                    "quantity": 2,
                    "price": 181.0,
                    "gross_transaction_amount": 362.0,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ]
        },
    )
    _call(
        results,
        name="ingest portfolio bundle",
        method="POST",
        url=f"{ingest}/ingest/portfolio-bundle",
        expected={202},
        json={
            "source_system": "SMOKE",
            "mode": "UPSERT",
            "business_dates": [{"business_date": trade_date}],
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2024-01-01",
                    "risk_exposure": "Medium",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Discretionary",
                    "booking_center_code": "SGP",
                    "client_id": "CLIENT_SMOKE_001",
                    "status": "Active",
                }
            ],
            "instruments": [
                {
                    "security_id": security_id,
                    "isin": isin,
                    "name": "Smoke Asset",
                    "currency": "USD",
                    "product_type": "Equity",
                }
            ],
            "market_prices": [
                {
                    "security_id": security_id,
                    "price": 180.25,
                    "currency": "USD",
                    "price_date": trade_date,
                }
            ],
            "fx_rates": [
                {
                    "from_currency": "USD",
                    "to_currency": "CHF",
                    "rate": 0.9,
                    "rate_date": trade_date,
                }
            ],
            "transactions": [
                {
                    "transaction_id": f"TXB_SMOKE_{run_id}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": instrument_id,
                    "security_id": security_id,
                    "transaction_date": trade_timestamp,
                    "transaction_type": "BUY",
                    "quantity": 1,
                    "price": 180.25,
                    "gross_transaction_amount": 180.25,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ],
        },
    )

    with tmp_csv.open("rb") as handle:
        _call(
            results,
            name="upload preview",
            method="POST",
            url=f"{ingest}/ingest/uploads/preview",
            expected={200},
            files={"file": ("smoke.csv", handle, "text/csv")},
            data={"entity_type": "transactions", "sample_size": "5"},
        )

    with tmp_csv.open("rb") as handle:
        _call(
            results,
            name="upload commit",
            method="POST",
            url=f"{ingest}/ingest/uploads/commit",
            expected={202},
            files={"file": ("smoke.csv", handle, "text/csv")},
            data={"entity_type": "transactions", "allow_partial": "true"},
        )

    jobs_response = _call(
        results,
        name="jobs list",
        method="GET",
        url=f"{ingest}/ingestion/jobs?limit=10",
        expected={200},
        headers=ops_headers,
    )
    job_id: str | None = None
    if jobs_response is not None and jobs_response.status_code == 200:
        payload = jobs_response.json()
        jobs = payload.get("jobs") or payload.get("data") or []
        if jobs:
            job_id = jobs[0].get("job_id")
    if job_id:
        _call(
            results,
            name="job get",
            method="GET",
            url=f"{ingest}/ingestion/jobs/{job_id}",
            expected={200},
            headers=ops_headers,
        )
        _call(
            results,
            name="job failures",
            method="GET",
            url=f"{ingest}/ingestion/jobs/{job_id}/failures",
            expected={200},
            headers=ops_headers,
        )
        _call(
            results,
            name="job record status",
            method="GET",
            url=f"{ingest}/ingestion/jobs/{job_id}/records",
            expected={200},
            headers=ops_headers,
        )
        _call(
            results,
            name="job retry dry run",
            method="POST",
            url=f"{ingest}/ingestion/jobs/{job_id}/retry",
            expected={200},
            headers=ops_headers,
            json={"dry_run": True, "record_keys": []},
        )
    else:
        results.append(
            CheckResult(
                name="job get",
                method="GET",
                url=f"{ingest}/ingestion/jobs/{{job_id}}",
                status=0,
                ok=False,
                note="job_id not discovered from list response",
                response=None,
            )
        )

    _call(
        results,
        name="health summary",
        method="GET",
        url=f"{ingest}/ingestion/health/summary",
        expected={200},
        headers=ops_headers,
    )
    _call(
        results,
        name="health lag",
        method="GET",
        url=f"{ingest}/ingestion/health/lag",
        expected={200},
        headers=ops_headers,
    )
    _call(
        results,
        name="health slo",
        method="GET",
        url=f"{ingest}/ingestion/health/slo",
        expected={200},
        headers=ops_headers,
    )
    _call(
        results,
        name="health consumer lag",
        method="GET",
        url=f"{ingest}/ingestion/health/consumer-lag",
        expected={200},
        headers=ops_headers,
    )
    _call(
        results,
        name="health error budget",
        method="GET",
        url=f"{ingest}/ingestion/health/error-budget",
        expected={200},
        headers=ops_headers,
    )
    operating_band_response = _call(
        results,
        name="health operating band",
        method="GET",
        url=f"{ingest}/ingestion/health/operating-band",
        expected={200},
        headers=ops_headers,
    )
    policy_response = _call(
        results,
        name="health policy",
        method="GET",
        url=f"{ingest}/ingestion/health/policy",
        expected={200},
        headers=ops_headers,
    )
    reprocessing_queue_response = _call(
        results,
        name="health reprocessing queue",
        method="GET",
        url=f"{ingest}/ingestion/health/reprocessing-queue",
        expected={200},
        headers=ops_headers,
    )
    backlog_breakdown_response = _call(
        results,
        name="health backlog breakdown",
        method="GET",
        url=f"{ingest}/ingestion/health/backlog-breakdown",
        expected={200},
        headers=ops_headers,
    )
    stalled_jobs_response = _call(
        results,
        name="health stalled jobs",
        method="GET",
        url=f"{ingest}/ingestion/health/stalled-jobs",
        expected={200},
        headers=ops_headers,
    )
    capacity_response = _call(
        results,
        name="health capacity",
        method="GET",
        url=f"{ingest}/ingestion/health/capacity",
        expected={200},
        headers=ops_headers,
    )

    policy_payload = _response_json_or_none(policy_response)
    if isinstance(policy_payload, dict):
        required_policy_keys = {
            "policy_version",
            "policy_fingerprint",
            "calculator_peak_lag_age_seconds",
            "replay_isolation_mode",
            "partition_growth_strategy",
        }
        missing_policy_keys = sorted(required_policy_keys - set(policy_payload))
        _record_contract_check(
            results,
            name="health policy contract",
            url=f"{ingest}/ingestion/health/policy",
            ok=not missing_policy_keys,
            note=(
                "all required policy keys present"
                if not missing_policy_keys
                else f"missing policy keys: {', '.join(missing_policy_keys)}"
            ),
            response=policy_payload,
        )

    capacity_payload = _response_json_or_none(capacity_response)
    if isinstance(capacity_payload, dict):
        required_capacity_keys = {
            "as_of",
            "lookback_minutes",
            "assumed_replicas",
            "total_backlog_records",
            "groups",
        }
        missing_capacity_keys = sorted(required_capacity_keys - set(capacity_payload))
        group_contract_ok = True
        group_contract_note = "capacity contract fields present"
        groups = capacity_payload.get("groups")
        if isinstance(groups, list) and groups:
            required_group_keys = {
                "lambda_in_events_per_second",
                "mu_msg_per_replica_events_per_second",
                "effective_capacity_events_per_second",
                "utilization_ratio",
                "headroom_ratio",
                "saturation_state",
            }
            missing_group_keys = sorted(required_group_keys - set(groups[0]))
            if missing_group_keys:
                group_contract_ok = False
                group_contract_note = (
                    f"missing capacity group keys: {', '.join(missing_group_keys)}"
                )
        elif missing_capacity_keys:
            group_contract_ok = False
        _record_contract_check(
            results,
            name="health capacity contract",
            url=f"{ingest}/ingestion/health/capacity",
            ok=(not missing_capacity_keys) and group_contract_ok,
            note=(
                group_contract_note
                if not missing_capacity_keys
                else f"missing capacity keys: {', '.join(missing_capacity_keys)}"
            ),
            response=capacity_payload,
        )

    operating_band_payload = _response_json_or_none(operating_band_response)
    if operating_band_response is not None:
        _record_contract_check(
            results,
            name="health operating band contract",
            url=f"{ingest}/ingestion/health/operating-band",
            ok=isinstance(operating_band_payload, dict),
            note="operating band payload captured",
            response=operating_band_payload,
        )
    reprocessing_queue_payload = _response_json_or_none(reprocessing_queue_response)
    if reprocessing_queue_response is not None:
        _record_contract_check(
            results,
            name="health reprocessing queue contract",
            url=f"{ingest}/ingestion/health/reprocessing-queue",
            ok=isinstance(reprocessing_queue_payload, dict),
            note="reprocessing queue payload captured",
            response=reprocessing_queue_payload,
        )
    backlog_breakdown_payload = _response_json_or_none(backlog_breakdown_response)
    if backlog_breakdown_response is not None:
        _record_contract_check(
            results,
            name="health backlog breakdown contract",
            url=f"{ingest}/ingestion/health/backlog-breakdown",
            ok=isinstance(backlog_breakdown_payload, dict),
            note="backlog breakdown payload captured",
            response=backlog_breakdown_payload,
        )
    stalled_jobs_payload = _response_json_or_none(stalled_jobs_response)
    if stalled_jobs_response is not None:
        _record_contract_check(
            results,
            name="health stalled jobs contract",
            url=f"{ingest}/ingestion/health/stalled-jobs",
            ok=isinstance(stalled_jobs_payload, dict),
            note="stalled jobs payload captured",
            response=stalled_jobs_payload,
        )

    _call(
        results,
        name="dlq list",
        method="GET",
        url=f"{ingest}/ingestion/dlq/consumer-events?limit=10",
        expected={200},
        headers=ops_headers,
    )
    _call(
        results,
        name="idempotency diagnostics",
        method="GET",
        url=f"{ingest}/ingestion/idempotency/diagnostics?limit=10",
        expected={200},
        headers=ops_headers,
    )
    _call(
        results,
        name="reprocess tx",
        method="POST",
        url=f"{ingest}/reprocess/transactions",
        expected={202},
        json={"transaction_ids": [transaction_id]},
    )

    _wait_portfolio_visible(
        query_base_url=query,
        portfolio_id=portfolio_id,
        timeout_seconds=args.query_visible_timeout_seconds,
    )

    _call(results, name="query live", method="GET", url=f"{query}/health/live", expected={200})
    _call(results, name="query ready", method="GET", url=f"{query}/health/ready", expected={200})
    _call(results, name="query metrics", method="GET", url=f"{query}/metrics", expected={200})
    _call(
        results,
        name="portfolios list",
        method="GET",
        url=f"{query}/portfolios/?portfolio_id={portfolio_id}",
        expected={200},
    )
    _call(
        results,
        name="portfolio get",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}",
        expected={200},
    )
    _call(
        results,
        name="positions",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/positions",
        expected={200},
    )
    _call(
        results,
        name="position history",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/position-history?security_id={security_id}",
        expected={200},
    )
    _call(
        results,
        name="transactions",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/transactions",
        expected={200},
    )
    _call(
        results,
        name="cash linkage",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage",
        expected={200, 404},
    )
    _call(
        results,
        name="lots",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/positions/{security_id}/lots",
        expected={200},
    )
    _call(
        results,
        name="accrued offsets",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets",
        expected={200},
    )
    _call(
        results,
        name="support overview",
        method="GET",
        url=f"{query}/support/portfolios/{portfolio_id}/overview",
        expected={200},
    )
    _call(
        results,
        name="support valuation jobs",
        method="GET",
        url=f"{query}/support/portfolios/{portfolio_id}/valuation-jobs",
        expected={200},
    )
    _call(
        results,
        name="support aggregation jobs",
        method="GET",
        url=f"{query}/support/portfolios/{portfolio_id}/aggregation-jobs",
        expected={200},
    )
    _call(
        results,
        name="lineage keys",
        method="GET",
        url=f"{query}/lineage/portfolios/{portfolio_id}/keys",
        expected={200},
    )
    _call(
        results,
        name="lineage security",
        method="GET",
        url=f"{query}/lineage/portfolios/{portfolio_id}/securities/{security_id}",
        expected={200, 404},
    )
    _call(
        results,
        name="prices",
        method="GET",
        url=f"{query}/prices/?security_id={security_id}",
        expected={200},
    )
    _call(
        results,
        name="fx rates",
        method="GET",
        url=f"{query}/fx-rates/?from_currency=USD&to_currency=CHF",
        expected={200},
    )
    _call(
        results,
        name="instruments",
        method="GET",
        url=f"{query}/instruments/?security_id={security_id}",
        expected={200},
    )
    _call(
        results,
        name="lookups portfolios",
        method="GET",
        url=f"{query}/lookups/portfolios?limit=50",
        expected={200},
    )
    _call(
        results,
        name="lookups instruments",
        method="GET",
        url=f"{query}/lookups/instruments?limit=50",
        expected={200},
    )
    _call(
        results,
        name="lookups currencies",
        method="GET",
        url=f"{query}/lookups/currencies?limit=50",
        expected={200},
    )
    _call(
        results,
        name="integration capabilities",
        method="GET",
        url=f"{query}/integration/capabilities",
        expected={200},
    )
    _call(
        results,
        name="integration policy",
        method="GET",
        url=f"{query}/integration/policy/effective",
        expected={200},
    )
    _call(
        results,
        name="enrichment bulk",
        method="POST",
        url=f"{query}/integration/instruments/enrichment-bulk",
        expected={200},
        json={"security_ids": [security_id]},
    )
    _call(
        results,
        name="core snapshot",
        method="POST",
        url=f"{query}/integration/portfolios/{portfolio_id}/core-snapshot",
        expected={200},
        json={
            "as_of_date": trade_date,
            "snapshot_mode": "BASELINE",
            "sections": ["positions_baseline", "portfolio_totals"],
        },
    )

    session_response = _call(
        results,
        name="simulation create",
        method="POST",
        url=f"{query}/simulation-sessions",
        expected={200, 201},
        json={"portfolio_id": portfolio_id, "created_by": "deterministic_smoke", "ttl_hours": 1},
    )
    session_id: str | None = None
    if session_response is not None and session_response.status_code in {200, 201}:
        body = session_response.json()
        session_id = body.get("session_id")
    if session_id:
        _call(
            results,
            name="simulation get",
            method="GET",
            url=f"{query}/simulation-sessions/{session_id}",
            expected={200},
        )
        _call(
            results,
            name="simulation changes upsert",
            method="POST",
            url=f"{query}/simulation-sessions/{session_id}/changes",
            expected={200, 201},
            json={
                "changes": [
                    {
                        "change_type": "TRANSACTION",
                        "transaction": {
                            "transaction_id": f"SIMTX_SMOKE_{run_id}",
                            "portfolio_id": portfolio_id,
                            "instrument_id": instrument_id,
                            "security_id": security_id,
                            "transaction_date": trade_timestamp,
                            "transaction_type": "BUY",
                            "quantity": 1,
                            "price": 180.25,
                            "gross_transaction_amount": 180.25,
                            "trade_currency": "USD",
                            "currency": "USD",
                        },
                    }
                ]
            },
        )
        _call(
            results,
            name="simulation projected positions",
            method="GET",
            url=f"{query}/simulation-sessions/{session_id}/projected-positions",
            expected={200},
        )
        _call(
            results,
            name="simulation projected summary",
            method="GET",
            url=f"{query}/simulation-sessions/{session_id}/projected-summary",
            expected={200},
        )
        _call(
            results,
            name="simulation delete",
            method="DELETE",
            url=f"{query}/simulation-sessions/{session_id}",
            expected={200, 204},
        )

    try:
        tmp_csv.unlink(missing_ok=True)
    except Exception:
        pass

    failures = [item for item in results if not item.ok]
    summary = {
        "run_id": run_id,
        "portfolio_id": portfolio_id,
        "security_id": security_id,
        "isin": isin,
        "passed": len(results) - len(failures),
        "failed": len(failures),
    }
    json_path, md_path = _write_report(
        output_dir=(repo_root / args.output_dir),
        run_id=run_id,
        summary=summary,
        results=results,
    )

    print(f"Wrote: {json_path}")
    print(f"Wrote: {md_path}")
    print(f"Passed: {summary['passed']} Failed: {summary['failed']}")
    if failures:
        print("Failed checks:")
        for item in failures:
            print(f"- {item.name}: status={item.status} note={item.note}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
