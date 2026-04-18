"""Collect reconciliation evidence for an existing bank-day load run."""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import create_engine, text

try:
    from scripts.bank_day_load_scenario import (
        DEFAULT_HOST_DATABASE_URL,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_QUERY_BASE_URL,
        DEFAULT_QUERY_CONTROL_BASE_URL,
        DEFAULT_RECONCILIATION_BASE_URL,
        ApiProbeResult,
        SamplePortfolioResult,
        _build_instrument_specs,
        _collect_sample_portfolios,
        _utc_now,
        expected_portfolio_market_value,
    )
except ModuleNotFoundError:
    from bank_day_load_scenario import (
        DEFAULT_HOST_DATABASE_URL,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_QUERY_BASE_URL,
        DEFAULT_QUERY_CONTROL_BASE_URL,
        DEFAULT_RECONCILIATION_BASE_URL,
        ApiProbeResult,
        SamplePortfolioResult,
        _build_instrument_specs,
        _collect_sample_portfolios,
        _utc_now,
        expected_portfolio_market_value,
    )


@dataclass(frozen=True)
class ProbeLatencySummary:
    label: str
    probe_count: int
    status_codes: list[int]
    median_ms: float | None
    p95_ms: float | None


@dataclass(frozen=True)
class ReconciliationSummary:
    all_samples_reconciled: bool
    all_position_counts_match_expected: bool
    all_transaction_counts_match_expected: bool
    all_market_values_match_expected: bool
    expected_portfolio_market_value: str
    positions_latency: ProbeLatencySummary
    transactions_latency: ProbeLatencySummary
    support_latency: ProbeLatencySummary


@dataclass(frozen=True)
class ExistingRunReconciliationReport:
    run_id: str
    captured_at_utc: str
    business_date: str
    portfolio_count_evaluated: int
    sample_portfolio_ids: list[str]
    run_progress: dict[str, Any]
    sample_portfolios: list[SamplePortfolioResult]
    api_probes: list[ApiProbeResult]
    summary: ReconciliationSummary


def _fetch_portfolio_ids(
    *,
    host_database_url: str,
    run_id: str,
    portfolio_limit: int | None,
) -> list[str]:
    engine = create_engine(host_database_url, future=True)
    stmt = text(
        """
        SELECT portfolio_id
        FROM portfolios
        WHERE portfolio_id LIKE :pattern
        ORDER BY portfolio_id
        """
    )
    if portfolio_limit is not None:
        stmt = text(
            """
            SELECT portfolio_id
            FROM portfolios
            WHERE portfolio_id LIKE :pattern
            ORDER BY portfolio_id
            LIMIT :portfolio_limit
            """
        )
    with engine.connect() as connection:
        rows = connection.execute(
            stmt,
            {
                "pattern": f"LOAD_{run_id}_PF_%",
                "portfolio_limit": portfolio_limit,
            },
        ).fetchall()
    return [row[0] for row in rows]


def _summarize_probe_group(
    *,
    label: str,
    api_probes: list[ApiProbeResult],
    endpoint_token: str,
) -> ProbeLatencySummary:
    matching = [probe for probe in api_probes if endpoint_token in probe.endpoint]
    samples = [sample for probe in matching for sample in probe.latency_ms_samples]
    return ProbeLatencySummary(
        label=label,
        probe_count=len(matching),
        status_codes=sorted({probe.status_code for probe in matching}),
        median_ms=round(statistics.median(samples), 3) if samples else None,
        p95_ms=round(max(probe.p95_ms for probe in matching), 3) if matching else None,
    )


def _build_summary(
    *,
    sample_portfolios: list[SamplePortfolioResult],
    api_probes: list[ApiProbeResult],
    expected_positions_count: int,
    expected_transactions_count: int,
    expected_market_value: str,
) -> ReconciliationSummary:
    return ReconciliationSummary(
        all_samples_reconciled=all(
            sample.reconciliation_passed for sample in sample_portfolios
        ),
        all_position_counts_match_expected=all(
            sample.positions_count == expected_positions_count for sample in sample_portfolios
        ),
        all_transaction_counts_match_expected=all(
            sample.transactions_count == expected_transactions_count
            for sample in sample_portfolios
        ),
        all_market_values_match_expected=all(
            sample.total_market_value == expected_market_value for sample in sample_portfolios
        ),
        expected_portfolio_market_value=expected_market_value,
        positions_latency=_summarize_probe_group(
            label="positions",
            api_probes=api_probes,
            endpoint_token="/positions?",
        ),
        transactions_latency=_summarize_probe_group(
            label="transactions",
            api_probes=api_probes,
            endpoint_token="/transactions?",
        ),
        support_latency=_summarize_probe_group(
            label="support_overview",
            api_probes=api_probes,
            endpoint_token="/support/portfolios/",
        ),
    )


def _write_report(
    *,
    report: ExistingRunReconciliationReport,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp_token = report.captured_at_utc.replace(":", "").replace("-", "")[:15]
    base_name = f"{timestamp_token}-bank-day-load-reconciliation"
    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"
    json_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    handoff_pressure_hint = (
        report.run_progress.get("valuation_to_position_timeseries_handoff_pressure_hint") or "n/a"
    )
    markdown = [
        f"# Bank-day load reconciliation {report.run_id}",
        "",
        f"- Captured at UTC: `{report.captured_at_utc}`",
        f"- Business date: `{report.business_date}`",
        f"- Portfolios evaluated: `{report.portfolio_count_evaluated}`",
        "",
        "## Summary",
        "",
        f"- all samples reconciled: `{report.summary.all_samples_reconciled}`",
        (
            f"- all position counts matched expected: "
            f"`{report.summary.all_position_counts_match_expected}`"
        ),
        (
            f"- all transaction counts matched expected: "
            f"`{report.summary.all_transaction_counts_match_expected}`"
        ),
        (
            f"- all market values matched expected "
            f"`{report.summary.expected_portfolio_market_value}`: "
            f"`{report.summary.all_market_values_match_expected}`"
        ),
        "",
        "## Run progress",
        "",
        f"- run state: `{report.run_progress.get('run_state', 'UNKNOWN')}`",
        (
            f"- complete portfolios: `{report.run_progress.get('complete_portfolios', 'n/a')}` / "
            f"`{report.run_progress.get('portfolios_ingested', 'n/a')}`"
        ),
        (
            f"- incomplete portfolios: "
            f"`{report.run_progress.get('incomplete_portfolios', 'n/a')}`"
        ),
        (
            f"- waiting for snapshots: "
            f"`{report.run_progress.get('portfolios_waiting_for_snapshots', 'n/a')}`"
        ),
        (
            f"- waiting for position timeseries: "
            f"`{report.run_progress.get('portfolios_waiting_for_position_timeseries', 'n/a')}`"
        ),
        (
            f"- waiting for portfolio timeseries: "
            f"`{report.run_progress.get('portfolios_waiting_for_portfolio_timeseries', 'n/a')}`"
        ),
        (
            f"- handoff pressure hint: "
            f"`{handoff_pressure_hint}`"
        ),
        "",
        "```json",
        json.dumps(report.run_progress, indent=2),
        "```",
        "",
        "## Sample portfolios",
        "",
        "```json",
        json.dumps([asdict(sample) for sample in report.sample_portfolios], indent=2),
        "```",
        "",
        "## API probes",
        "",
        "```json",
        json.dumps([asdict(probe) for probe in report.api_probes], indent=2),
        "```",
    ]
    md_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--business-date", required=True)
    parser.add_argument("--transactions-per-portfolio", type=int, default=100)
    parser.add_argument("--portfolio-limit", type=int, default=5)
    parser.add_argument("--query-base-url", default=DEFAULT_QUERY_BASE_URL)
    parser.add_argument("--query-control-base-url", default=DEFAULT_QUERY_CONTROL_BASE_URL)
    parser.add_argument("--reconciliation-base-url", default=DEFAULT_RECONCILIATION_BASE_URL)
    parser.add_argument("--host-database-url", default=DEFAULT_HOST_DATABASE_URL)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--positions-probe-repetitions", type=int, default=1)
    parser.add_argument("--transactions-probe-repetitions", type=int, default=1)
    parser.add_argument("--support-probe-repetitions", type=int, default=1)
    args = parser.parse_args()

    portfolio_ids = _fetch_portfolio_ids(
        host_database_url=args.host_database_url,
        run_id=args.run_id,
        portfolio_limit=args.portfolio_limit,
    )
    if not portfolio_ids:
        raise SystemExit(f"No portfolios found for run {args.run_id}.")

    run_progress_url = (
        f"{args.query_control_base_url}/support/load-runs/{args.run_id}"
        f"?business_date={args.business_date}"
    )
    session = requests.Session()
    run_progress_response = session.get(run_progress_url, timeout=60)
    run_progress_response.raise_for_status()
    run_progress = run_progress_response.json()

    specs = _build_instrument_specs(
        run_id=args.run_id,
        instrument_count=args.transactions_per_portfolio,
    )
    sample_portfolios, api_probes = _collect_sample_portfolios(
        session=session,
        query_base_url=args.query_base_url,
        query_control_base_url=args.query_control_base_url,
        reconciliation_base_url=args.reconciliation_base_url,
        portfolios=[{"portfolio_id": portfolio_id} for portfolio_id in portfolio_ids],
        specs=specs,
        trade_date=args.business_date,
        sample_size=len(portfolio_ids),
        positions_probe_repetitions=args.positions_probe_repetitions,
        transactions_probe_repetitions=args.transactions_probe_repetitions,
        support_probe_repetitions=args.support_probe_repetitions,
    )

    expected_market_value = f"{expected_portfolio_market_value(specs):.10f}"
    report = ExistingRunReconciliationReport(
        run_id=args.run_id,
        captured_at_utc=run_progress["generated_at_utc"] or _utc_now(),
        business_date=args.business_date,
        portfolio_count_evaluated=len(portfolio_ids),
        sample_portfolio_ids=portfolio_ids,
        run_progress=run_progress,
        sample_portfolios=sample_portfolios,
        api_probes=api_probes,
        summary=_build_summary(
            sample_portfolios=sample_portfolios,
            api_probes=api_probes,
            expected_positions_count=args.transactions_per_portfolio,
            expected_transactions_count=args.transactions_per_portfolio,
            expected_market_value=expected_market_value,
        ),
    )
    json_path, md_path = _write_report(report=report, output_dir=Path(args.output_dir))
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
