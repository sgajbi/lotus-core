"""Governed bank-day load scenario runner for lotus-core.

This script seeds a deterministic banking-day workload through lotus-core's
ingestion APIs, waits for the asynchronous processing pipeline to drain, then
collects evidence across throughput, reconciliation, API responses, operator
health, and log posture.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import requests
from portfolio_common.db import get_sync_database_url
from sqlalchemy import create_engine, text

DEFAULT_INGESTION_BASE_URL = "http://localhost:8200"
DEFAULT_QUERY_BASE_URL = "http://localhost:8201"
DEFAULT_QUERY_CONTROL_BASE_URL = "http://localhost:8202"
DEFAULT_EVENT_REPLAY_BASE_URL = "http://localhost:8209"
DEFAULT_RECONCILIATION_BASE_URL = "http://localhost:8210"
DEFAULT_OUTPUT_DIR = "output/task-runs"
DEFAULT_OPS_TOKEN = os.getenv("LOTUS_CORE_INGEST_OPS_TOKEN", "lotus-core-ops-local")
DEFAULT_HOST_DATABASE_URL = os.getenv(
    "HOST_DATABASE_URL",
    "postgresql://user:password@localhost:55432/portfolio_db",
)

SUPPORTED_CURRENCIES = ("USD", "EUR", "SGD", "GBP")
USD_PER_CURRENCY: dict[str, Decimal] = {
    "USD": Decimal("1.000000"),
    "EUR": Decimal("1.100000"),
    "SGD": Decimal("0.740000"),
    "GBP": Decimal("1.270000"),
}
LOG_SERVICE_CONTAINERS = (
    "lotus-core-app-local-persistence_service-1",
    "lotus-core-app-local-position_calculator_service-1",
    "lotus-core-app-local-position_valuation_calculator-1",
    "lotus-core-app-local-portfolio_aggregation_service-1",
    "lotus-core-app-local-timeseries_generator_service-1",
    "lotus-core-app-local-pipeline_orchestrator_service-1",
    "lotus-core-app-local-query_service-1",
    "lotus-core-app-local-query_control_plane_service-1",
    "lotus-core-app-local-event_replay_service-1",
    "lotus-core-app-local-financial_reconciliation_service-1",
)


@dataclass(frozen=True)
class InstrumentSpec:
    security_id: str
    currency: str
    trade_price: Decimal
    market_price: Decimal


@dataclass(frozen=True)
class IngestPhaseResult:
    endpoint: str
    record_count: int
    batch_count: int
    duration_seconds: float


@dataclass(frozen=True)
class ApiProbeResult:
    endpoint: str
    status_code: int
    latency_ms_samples: list[float]
    p95_ms: float
    median_ms: float
    check_passed: bool
    failure_detail: str | None


@dataclass(frozen=True)
class SamplePortfolioResult:
    portfolio_id: str
    positions_count: int
    transactions_count: int
    support_publish_allowed: bool
    support_pending_valuation_jobs: int
    support_pending_aggregation_jobs: int
    support_latest_booked_position_snapshot_date: str | None
    total_market_value: str
    expected_market_value: str
    reconciliation_passed: bool
    reconciliation_finding_count: int


@dataclass(frozen=True)
class DatabaseTieOut:
    portfolios_count: int
    instruments_count: int
    transactions_count: int
    portfolios_with_snapshots: int
    snapshots_count: int
    portfolios_with_position_timeseries: int
    complete_portfolios: int
    incomplete_portfolios: int
    portfolios_waiting_for_snapshots: int
    snapshot_portfolios_without_position_timeseries: int
    position_timeseries_count: int
    portfolios_with_portfolio_timeseries: int
    portfolios_waiting_for_position_timeseries: int
    position_timeseries_portfolios_without_portfolio_timeseries: int
    portfolios_waiting_for_portfolio_timeseries: int
    portfolio_timeseries_count: int
    summed_snapshot_quantity: str
    expected_total_quantity: str
    summed_snapshot_market_value: str
    expected_total_market_value: str
    per_security_quantity_min: str | None
    per_security_quantity_max: str | None
    pending_valuation_jobs: int
    processing_valuation_jobs: int
    open_valuation_jobs: int
    pending_aggregation_jobs: int
    processing_aggregation_jobs: int
    open_aggregation_jobs: int
    latest_snapshot_materialized_at_utc: str | None
    latest_position_timeseries_materialized_at_utc: str | None
    latest_portfolio_timeseries_materialized_at_utc: str | None
    latest_valuation_job_updated_at_utc: str | None
    latest_aggregation_job_updated_at_utc: str | None
    completed_valuation_jobs_without_position_timeseries: int
    oldest_completed_valuation_without_position_timeseries_at_utc: str | None
    valuation_to_position_timeseries_latency_sample_count: int
    valuation_to_position_timeseries_latency_p50_seconds: float | None
    valuation_to_position_timeseries_latency_p95_seconds: float | None
    valuation_to_position_timeseries_latency_max_seconds: float | None


@dataclass(frozen=True)
class HealthSample:
    captured_at: str
    backlog_jobs: int
    backlog_age_seconds: float
    dlq_events_in_window: int
    replay_pressure_ratio: float


@dataclass(frozen=True)
class LogEvidence:
    container_name: str
    error_line_count: int
    sample_error_lines: list[str]


@dataclass(frozen=True)
class ScenarioReport:
    scenario_name: str
    run_id: str
    terminal_status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    config: dict[str, Any]
    ingest_phases: list[IngestPhaseResult]
    drain_seconds: float
    peak_backlog_jobs: int
    peak_backlog_age_seconds: float
    peak_replay_pressure_ratio: float
    peak_dlq_events_in_window: int
    health_samples: list[HealthSample]
    database_tie_out: DatabaseTieOut
    sample_portfolios: list[SamplePortfolioResult]
    api_probes: list[ApiProbeResult]
    log_evidence: list[LogEvidence]
    checks_passed: bool
    failures: list[str]


class HealthMonitor:
    def __init__(
        self,
        *,
        event_replay_base_url: str,
        ops_token: str,
        interval_seconds: float,
    ) -> None:
        self._event_replay_base_url = event_replay_base_url
        self._ops_token = ops_token
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.samples: list[HealthSample] = []

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        session = requests.Session()
        headers = {"X-Lotus-Ops-Token": self._ops_token}
        while not self._stop_event.is_set():
            try:
                summary = session.get(
                    f"{self._event_replay_base_url}/ingestion/health/summary",
                    headers=headers,
                    timeout=15,
                )
                slo = session.get(
                    f"{self._event_replay_base_url}/ingestion/health/slo?lookback_minutes=60",
                    headers=headers,
                    timeout=15,
                )
                budget = session.get(
                    f"{self._event_replay_base_url}/ingestion/health/error-budget?lookback_minutes=60",
                    headers=headers,
                    timeout=15,
                )
                if (
                    summary.status_code == 200
                    and slo.status_code == 200
                    and budget.status_code == 200
                ):
                    summary_payload = summary.json()
                    slo_payload = slo.json()
                    budget_payload = budget.json()
                    self.samples.append(
                        HealthSample(
                            captured_at=_utc_now(),
                            backlog_jobs=int(summary_payload.get("backlog_jobs", 0)),
                            backlog_age_seconds=float(
                                slo_payload.get("backlog_age_seconds", 0.0)
                            ),
                            dlq_events_in_window=int(
                                budget_payload.get("dlq_events_in_window", 0)
                            ),
                            replay_pressure_ratio=float(
                                budget_payload.get(
                                    "replay_backlog_pressure_ratio",
                                    0.0,
                                )
                            ),
                        )
                    )
            except requests.RequestException:
                pass
            self._stop_event.wait(self._interval_seconds)


class RateLimitError(RuntimeError):
    """Raised when the ingestion API rejects a batch due to rate limiting."""


class ScenarioInterrupted(RuntimeError):
    """Raised when the scenario receives an interrupt signal."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _decimal_str(value: Decimal) -> str:
    return f"{value:.10f}"


def _parse_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _percentile(samples: list[float], percentile: int) -> float:
    if not samples:
        return 0.0
    if len(samples) == 1:
        return samples[0]
    index = max(0, min(percentile - 1, 99))
    return statistics.quantiles(samples, n=100)[index]


def _fx_rate(from_currency: str, to_currency: str) -> Decimal:
    if from_currency == to_currency:
        return Decimal("1.000000")
    return (USD_PER_CURRENCY[from_currency] / USD_PER_CURRENCY[to_currency]).quantize(
        Decimal("0.000001")
    )


def _build_portfolios(
    *,
    run_id: str,
    portfolio_count: int,
    trade_date: str,
) -> list[dict[str, Any]]:
    open_date = date.fromisoformat(trade_date).replace(day=1).isoformat()
    return [
        {
            "portfolio_id": f"LOAD_{run_id}_PF_{index:04d}",
            "portfolio_name": f"Load Test Portfolio {index:04d}",
            "base_currency": "USD",
            "open_date": open_date,
            "risk_exposure": "BALANCED",
            "investment_time_horizon": "MEDIUM_TERM",
            "portfolio_type": "DISCRETIONARY",
            "booking_center_code": "PB_SG",
            "client_id": f"LOAD_{run_id}_CLIENT_{index:04d}",
            "status": "ACTIVE",
        }
        for index in range(1, portfolio_count + 1)
    ]


def _build_instrument_specs(*, run_id: str, instrument_count: int) -> list[InstrumentSpec]:
    specs: list[InstrumentSpec] = []
    for index in range(instrument_count):
        currency = SUPPORTED_CURRENCIES[index % len(SUPPORTED_CURRENCIES)]
        trade_price = Decimal("50.00") + (Decimal(index) * Decimal("1.25"))
        market_price = (trade_price * Decimal("1.01")).quantize(Decimal("0.01"))
        specs.append(
            InstrumentSpec(
                security_id=f"LOAD_{run_id}_SEC_{index + 1:03d}",
                currency=currency,
                trade_price=trade_price.quantize(Decimal("0.01")),
                market_price=market_price,
            )
        )
    return specs


def _build_instruments_payload(specs: list[InstrumentSpec]) -> list[dict[str, Any]]:
    return [
        {
            "security_id": spec.security_id,
            "name": f"{spec.security_id} Common Stock",
            "isin": f"US{spec.security_id.replace('_', '')[-10:]}",
            "currency": spec.currency,
            "product_type": "STOCK",
            "asset_class": "EQUITY",
            "sector": "DIVERSIFIED",
            "country_of_risk": "SG",
        }
        for spec in specs
    ]


def _build_market_prices_payload(
    *,
    specs: list[InstrumentSpec],
    price_date: str,
) -> list[dict[str, Any]]:
    return [
        {
            "security_id": spec.security_id,
            "price_date": price_date,
            "price": f"{spec.market_price:.2f}",
            "currency": spec.currency,
        }
        for spec in specs
    ]


def _build_fx_rates_payload(
    *,
    currencies: Iterable[str],
    rate_date: str,
) -> list[dict[str, Any]]:
    rates: list[dict[str, Any]] = []
    for from_currency in currencies:
        for to_currency in currencies:
            if from_currency == to_currency:
                continue
            rates.append(
                {
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "rate_date": rate_date,
                    "rate": f"{_fx_rate(from_currency, to_currency):.6f}",
                }
            )
    return rates


def iter_transaction_batches(
    *,
    run_id: str,
    portfolios: list[dict[str, Any]],
    specs: list[InstrumentSpec],
    trade_date: str,
    transaction_batch_size: int,
) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    sequence = 1
    for portfolio in portfolios:
        portfolio_id = portfolio["portfolio_id"]
        for spec in specs:
            batch.append(
                {
                    "transaction_id": f"LOAD_{run_id}_TX_{sequence:08d}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": spec.security_id,
                    "security_id": spec.security_id,
                    "transaction_date": trade_date,
                    "transaction_type": "BUY",
                    "quantity": "1",
                    "price": f"{spec.trade_price:.2f}",
                    "gross_transaction_amount": f"{spec.trade_price:.2f}",
                    "trade_currency": spec.currency,
                    "currency": spec.currency,
                }
            )
            sequence += 1
            if len(batch) >= transaction_batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


def expected_portfolio_market_value(specs: list[InstrumentSpec]) -> Decimal:
    total = Decimal("0")
    for spec in specs:
        total += spec.market_price * _fx_rate(spec.currency, "USD")
    return total.quantize(Decimal("0.0000000001"))


def expected_total_market_value(
    *,
    portfolio_count: int,
    specs: list[InstrumentSpec],
) -> Decimal:
    return (
        expected_portfolio_market_value(specs) * Decimal(portfolio_count)
    ).quantize(Decimal("0.0000000001"))


def _wait_ready(*, base_urls: list[str], timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    session = requests.Session()
    while time.time() < deadline:
        try:
            statuses = [
                session.get(f"{base_url}/health/ready", timeout=5).status_code
                for base_url in base_urls
            ]
            if all(status == 200 for status in statuses):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("Services did not become ready before timeout.")


def _post_payload(
    *,
    session: requests.Session,
    base_url: str,
    endpoint: str,
    payload: dict[str, Any],
) -> None:
    response = session.post(f"{base_url}{endpoint}", json=payload, timeout=120)
    if response.status_code == 429:
        raise RateLimitError(
            f"POST {endpoint} failed with status=429: {response.text[:500]}"
        )
    if response.status_code not in {200, 201, 202}:
        raise RuntimeError(
            f"POST {endpoint} failed with status={response.status_code}: {response.text[:500]}"
        )


def _ingest_static_payload(
    *,
    session: requests.Session,
    base_url: str,
    endpoint: str,
    root_key: str,
    rows: list[dict[str, Any]],
) -> IngestPhaseResult:
    started = time.perf_counter()
    _post_payload(
        session=session,
        base_url=base_url,
        endpoint=endpoint,
        payload={root_key: rows},
    )
    return IngestPhaseResult(
        endpoint=endpoint,
        record_count=len(rows),
        batch_count=1,
        duration_seconds=round(time.perf_counter() - started, 3),
    )


def _ingest_transaction_batches(
    *,
    session: requests.Session,
    base_url: str,
    batches: Iterable[list[dict[str, Any]]],
    max_records_per_minute: int,
    max_requests_per_minute: int,
    rate_limit_sleep_seconds: int,
) -> IngestPhaseResult:
    started = time.perf_counter()
    record_count = 0
    batch_count = 0
    window_started = time.monotonic()
    window_records = 0
    window_requests = 0
    for batch in batches:
        while True:
            elapsed = time.monotonic() - window_started
            if elapsed >= 60:
                window_started = time.monotonic()
                window_records = 0
                window_requests = 0
                elapsed = 0
            would_exceed_records = window_records + len(batch) > max_records_per_minute
            would_exceed_requests = window_requests + 1 > max_requests_per_minute
            if would_exceed_records or would_exceed_requests:
                time.sleep(max(60 - elapsed, 1))
                continue
            try:
                _post_payload(
                    session=session,
                    base_url=base_url,
                    endpoint="/ingest/transactions",
                    payload={"transactions": batch},
                )
                window_records += len(batch)
                window_requests += 1
                break
            except RateLimitError:
                time.sleep(rate_limit_sleep_seconds)
                window_started = time.monotonic()
                window_records = 0
                window_requests = 0
        record_count += len(batch)
        batch_count += 1
    return IngestPhaseResult(
        endpoint="/ingest/transactions",
        record_count=record_count,
        batch_count=batch_count,
        duration_seconds=round(time.perf_counter() - started, 3),
    )


def _db_row(engine: Any, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(text(sql), params).mappings().one()
    return dict(row)


def _wait_for_cycle_completion(
    *,
    engine: Any,
    run_id: str,
    trade_date: str,
    portfolio_count: int,
    transaction_count: int,
    timeout_seconds: int,
) -> float:
    started = time.perf_counter()
    deadline = time.time() + timeout_seconds
    sql = """
    WITH portfolio_counts AS (
        SELECT count(*) AS portfolios_count
        FROM portfolios
        WHERE portfolio_id LIKE :portfolio_pattern
    ),
    transaction_counts AS (
        SELECT count(*) AS transactions_count
        FROM transactions
        WHERE transaction_id LIKE :transaction_pattern
    ),
    failed_val AS (
        SELECT count(*) AS failed_valuation_jobs
        FROM portfolio_valuation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND status = 'FAILED'
    ),
    failed_agg AS (
        SELECT count(*) AS failed_aggregation_jobs
        FROM portfolio_aggregation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND status = 'FAILED'
    ),
    snapshot_counts AS (
        SELECT count(*) AS snapshots_count
        FROM daily_position_snapshots
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date = :trade_date
    ),
    position_timeseries_counts AS (
        SELECT count(*) AS position_timeseries_count
        FROM position_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date = :trade_date
    ),
    timeseries_counts AS (
        SELECT count(*) AS portfolio_timeseries_count
        FROM portfolio_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date = :trade_date
    ),
    valuation_job_counts AS (
        SELECT
            count(*) FILTER (WHERE status = 'PENDING') AS pending_valuation_jobs,
            count(*) FILTER (WHERE status = 'PROCESSING') AS processing_valuation_jobs
        FROM portfolio_valuation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
    ),
    aggregation_job_counts AS (
        SELECT
            count(*) FILTER (WHERE status = 'PENDING') AS pending_aggregation_jobs,
            count(*) FILTER (WHERE status = 'PROCESSING') AS processing_aggregation_jobs
        FROM portfolio_aggregation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
    )
    SELECT *
    FROM portfolio_counts,
         transaction_counts,
         failed_val,
         failed_agg,
         snapshot_counts,
         position_timeseries_counts,
         timeseries_counts,
         valuation_job_counts,
         aggregation_job_counts
    """
    params = {
        "portfolio_pattern": f"LOAD_{run_id}_PF_%",
        "transaction_pattern": f"LOAD_{run_id}_TX_%",
        "trade_date": trade_date,
    }
    while time.time() < deadline:
        row = _db_row(engine, sql, params)
        if int(row["failed_valuation_jobs"]) > 0 or int(row["failed_aggregation_jobs"]) > 0:
            raise RuntimeError(
                "Pipeline entered FAILED state before drain: "
                f"failed_valuation_jobs={row['failed_valuation_jobs']} "
                f"failed_aggregation_jobs={row['failed_aggregation_jobs']}"
            )
        if (
            int(row["portfolios_count"]) == portfolio_count
            and int(row["transactions_count"]) == transaction_count
            and int(row["snapshots_count"]) == transaction_count
            and int(row["position_timeseries_count"]) == transaction_count
            and int(row["portfolio_timeseries_count"]) == portfolio_count
            and int(row["pending_valuation_jobs"] or 0) == 0
            and int(row["processing_valuation_jobs"] or 0) == 0
            and int(row["pending_aggregation_jobs"] or 0) == 0
            and int(row["processing_aggregation_jobs"] or 0) == 0
        ):
            return round(time.perf_counter() - started, 3)
        time.sleep(5)
    raise TimeoutError("Pipeline did not drain before timeout.")


def _wait_for_seed_materialization(
    *,
    engine: Any,
    sql: str,
    params: dict[str, Any],
    expected_count: int,
    label: str,
    timeout_seconds: int,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        row = _db_row(engine, sql, params)
        if int(row["count"]) >= expected_count:
            return
        time.sleep(2)
    raise TimeoutError(
        f"{label} materialization did not reach expected count {expected_count} before timeout."
    )


def _resolve_trade_date(*, engine: Any, explicit_trade_date: str | None) -> str:
    if explicit_trade_date:
        return explicit_trade_date
    row = _db_row(
        engine,
        """
        SELECT max(date) AS latest_business_date
        FROM business_dates
        """,
        {},
    )
    latest_business_date = row.get("latest_business_date")
    if latest_business_date is None:
        raise RuntimeError(
            "No business_dates rows exist. Provide --trade-date explicitly "
            "or seed business dates first."
        )
    return latest_business_date.isoformat()


def _build_database_tie_out(
    *,
    engine: Any,
    run_id: str,
    trade_date: str,
    portfolio_count: int,
    specs: list[InstrumentSpec],
) -> DatabaseTieOut:
    params = {
        "portfolio_pattern": f"LOAD_{run_id}_PF_%",
        "transaction_pattern": f"LOAD_{run_id}_TX_%",
        "security_pattern": f"LOAD_{run_id}_SEC_%",
        "trade_date": trade_date,
    }
    aggregate_row = _db_row(
        engine,
        """
        WITH security_quantities AS (
            SELECT security_id, sum(quantity) AS total_quantity
            FROM daily_position_snapshots
            WHERE portfolio_id LIKE :portfolio_pattern
              AND date = :trade_date
            GROUP BY security_id
        )
        SELECT
            (
                SELECT count(*)
                FROM portfolios
                WHERE portfolio_id LIKE :portfolio_pattern
            ) AS portfolios_count,
            (
                SELECT count(*)
                FROM instruments
                WHERE security_id LIKE :security_pattern
            ) AS instruments_count,
            (
                SELECT count(*)
                FROM transactions
                WHERE transaction_id LIKE :transaction_pattern
            ) AS transactions_count,
            (
                SELECT count(DISTINCT portfolio_id)
                FROM daily_position_snapshots
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS portfolios_with_snapshots,
            (
                SELECT count(*)
                FROM daily_position_snapshots
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS snapshots_count,
            (
                SELECT count(DISTINCT portfolio_id)
                FROM position_timeseries
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS portfolios_with_position_timeseries,
            (
                SELECT count(*)
                FROM position_timeseries
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS position_timeseries_count,
            (
                SELECT count(DISTINCT portfolio_id)
                FROM portfolio_timeseries
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS portfolios_with_portfolio_timeseries,
            (
                SELECT count(*)
                FROM portfolio_timeseries
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS portfolio_timeseries_count,
            (
                SELECT coalesce(sum(quantity), 0)
                FROM daily_position_snapshots
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS summed_snapshot_quantity,
            (
                SELECT coalesce(sum(market_value), 0)
                FROM daily_position_snapshots
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS summed_snapshot_market_value,
            (SELECT min(total_quantity) FROM security_quantities) AS per_security_quantity_min,
            (SELECT max(total_quantity) FROM security_quantities) AS per_security_quantity_max,
            (
                SELECT count(*) FILTER (WHERE status = 'PENDING')
                FROM portfolio_valuation_jobs
                WHERE portfolio_id LIKE :portfolio_pattern
            ) AS pending_valuation_jobs,
            (
                SELECT count(*) FILTER (WHERE status = 'PROCESSING')
                FROM portfolio_valuation_jobs
                WHERE portfolio_id LIKE :portfolio_pattern
            ) AS processing_valuation_jobs,
            (
                SELECT count(*) FILTER (WHERE status = 'PENDING')
                FROM portfolio_aggregation_jobs
                WHERE portfolio_id LIKE :portfolio_pattern
            ) AS pending_aggregation_jobs,
            (
                SELECT count(*) FILTER (WHERE status = 'PROCESSING')
                FROM portfolio_aggregation_jobs
                WHERE portfolio_id LIKE :portfolio_pattern
            ) AS processing_aggregation_jobs,
            (
                SELECT max(created_at)
                FROM daily_position_snapshots
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS latest_snapshot_materialized_at_utc,
            (
                SELECT max(created_at)
                FROM position_timeseries
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS latest_position_timeseries_materialized_at_utc,
            (
                SELECT max(created_at)
                FROM portfolio_timeseries
                WHERE portfolio_id LIKE :portfolio_pattern
                  AND date = :trade_date
            ) AS latest_portfolio_timeseries_materialized_at_utc,
            (
                SELECT max(updated_at)
                FROM portfolio_valuation_jobs
                WHERE portfolio_id LIKE :portfolio_pattern
            ) AS latest_valuation_job_updated_at_utc,
            (
                SELECT max(updated_at)
                FROM portfolio_aggregation_jobs
                WHERE portfolio_id LIKE :portfolio_pattern
            ) AS latest_aggregation_job_updated_at_utc,
            (
                SELECT count(*)
                FROM portfolio_valuation_jobs pvj
                LEFT JOIN position_timeseries pts
                  ON pts.portfolio_id = pvj.portfolio_id
                 AND pts.security_id = pvj.security_id
                 AND pts.date = pvj.valuation_date
                 AND pts.epoch = pvj.epoch
                WHERE pvj.portfolio_id LIKE :portfolio_pattern
                  AND pvj.status = 'COMPLETE'
                  AND pts.portfolio_id IS NULL
            ) AS completed_valuation_jobs_without_position_timeseries,
            (
                SELECT min(pvj.updated_at)
                FROM portfolio_valuation_jobs pvj
                LEFT JOIN position_timeseries pts
                  ON pts.portfolio_id = pvj.portfolio_id
                 AND pts.security_id = pvj.security_id
                 AND pts.date = pvj.valuation_date
                 AND pts.epoch = pvj.epoch
                WHERE pvj.portfolio_id LIKE :portfolio_pattern
                  AND pvj.status = 'COMPLETE'
                  AND pts.portfolio_id IS NULL
            ) AS oldest_completed_valuation_without_position_timeseries_at_utc,
            (
                SELECT count(*)
                FROM portfolio_valuation_jobs pvj
                JOIN position_timeseries pts
                  ON pts.portfolio_id = pvj.portfolio_id
                 AND pts.security_id = pvj.security_id
                 AND pts.date = pvj.valuation_date
                 AND pts.epoch = pvj.epoch
                WHERE pvj.portfolio_id LIKE :portfolio_pattern
                  AND pvj.status = 'COMPLETE'
            ) AS valuation_to_position_timeseries_latency_sample_count,
            (
                SELECT percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY GREATEST(EXTRACT(EPOCH FROM (pts.created_at - pvj.updated_at)), 0)
                )
                FROM portfolio_valuation_jobs pvj
                JOIN position_timeseries pts
                  ON pts.portfolio_id = pvj.portfolio_id
                 AND pts.security_id = pvj.security_id
                 AND pts.date = pvj.valuation_date
                 AND pts.epoch = pvj.epoch
                WHERE pvj.portfolio_id LIKE :portfolio_pattern
                  AND pvj.status = 'COMPLETE'
            ) AS valuation_to_position_timeseries_latency_p50_seconds,
            (
                SELECT percentile_cont(0.95) WITHIN GROUP (
                    ORDER BY GREATEST(EXTRACT(EPOCH FROM (pts.created_at - pvj.updated_at)), 0)
                )
                FROM portfolio_valuation_jobs pvj
                JOIN position_timeseries pts
                  ON pts.portfolio_id = pvj.portfolio_id
                 AND pts.security_id = pvj.security_id
                 AND pts.date = pvj.valuation_date
                 AND pts.epoch = pvj.epoch
                WHERE pvj.portfolio_id LIKE :portfolio_pattern
                  AND pvj.status = 'COMPLETE'
            ) AS valuation_to_position_timeseries_latency_p95_seconds,
            (
                SELECT max(GREATEST(EXTRACT(EPOCH FROM (pts.created_at - pvj.updated_at)), 0))
                FROM portfolio_valuation_jobs pvj
                JOIN position_timeseries pts
                  ON pts.portfolio_id = pvj.portfolio_id
                 AND pts.security_id = pvj.security_id
                 AND pts.date = pvj.valuation_date
                 AND pts.epoch = pvj.epoch
                WHERE pvj.portfolio_id LIKE :portfolio_pattern
                  AND pvj.status = 'COMPLETE'
            ) AS valuation_to_position_timeseries_latency_max_seconds
        """,
        params,
    )
    pending_valuation_jobs = int(aggregate_row["pending_valuation_jobs"] or 0)
    processing_valuation_jobs = int(aggregate_row["processing_valuation_jobs"] or 0)
    pending_aggregation_jobs = int(aggregate_row["pending_aggregation_jobs"] or 0)
    processing_aggregation_jobs = int(aggregate_row["processing_aggregation_jobs"] or 0)
    portfolios_count = int(aggregate_row["portfolios_count"])
    portfolios_with_snapshots = int(aggregate_row["portfolios_with_snapshots"])
    portfolios_with_position_timeseries = int(aggregate_row["portfolios_with_position_timeseries"])
    portfolios_with_portfolio_timeseries = int(
        aggregate_row["portfolios_with_portfolio_timeseries"]
    )
    return DatabaseTieOut(
        portfolios_count=portfolios_count,
        instruments_count=int(aggregate_row["instruments_count"]),
        transactions_count=int(aggregate_row["transactions_count"]),
        portfolios_with_snapshots=portfolios_with_snapshots,
        snapshots_count=int(aggregate_row["snapshots_count"]),
        portfolios_with_position_timeseries=portfolios_with_position_timeseries,
        complete_portfolios=portfolios_with_portfolio_timeseries,
        incomplete_portfolios=max(portfolios_count - portfolios_with_portfolio_timeseries, 0),
        portfolios_waiting_for_snapshots=max(
            portfolios_count - portfolios_with_snapshots,
            0,
        ),
        snapshot_portfolios_without_position_timeseries=max(
            portfolios_with_snapshots - portfolios_with_position_timeseries,
            0,
        ),
        position_timeseries_count=int(aggregate_row["position_timeseries_count"]),
        portfolios_with_portfolio_timeseries=portfolios_with_portfolio_timeseries,
        portfolios_waiting_for_position_timeseries=max(
            portfolios_with_snapshots - portfolios_with_position_timeseries,
            0,
        ),
        position_timeseries_portfolios_without_portfolio_timeseries=max(
            portfolios_with_position_timeseries - portfolios_with_portfolio_timeseries,
            0,
        ),
        portfolios_waiting_for_portfolio_timeseries=max(
            portfolios_with_position_timeseries - portfolios_with_portfolio_timeseries,
            0,
        ),
        portfolio_timeseries_count=int(aggregate_row["portfolio_timeseries_count"]),
        summed_snapshot_quantity=_decimal_str(
            _parse_decimal(aggregate_row["summed_snapshot_quantity"])
        ),
        expected_total_quantity=_decimal_str(Decimal(portfolio_count * len(specs))),
        summed_snapshot_market_value=_decimal_str(
            _parse_decimal(aggregate_row["summed_snapshot_market_value"])
        ),
        expected_total_market_value=_decimal_str(
            expected_total_market_value(portfolio_count=portfolio_count, specs=specs)
        ),
        per_security_quantity_min=(
            _decimal_str(_parse_decimal(aggregate_row["per_security_quantity_min"]))
            if aggregate_row["per_security_quantity_min"] is not None
            else None
        ),
        per_security_quantity_max=(
            _decimal_str(_parse_decimal(aggregate_row["per_security_quantity_max"]))
            if aggregate_row["per_security_quantity_max"] is not None
            else None
        ),
        pending_valuation_jobs=pending_valuation_jobs,
        processing_valuation_jobs=processing_valuation_jobs,
        open_valuation_jobs=pending_valuation_jobs + processing_valuation_jobs,
        pending_aggregation_jobs=pending_aggregation_jobs,
        processing_aggregation_jobs=processing_aggregation_jobs,
        open_aggregation_jobs=pending_aggregation_jobs + processing_aggregation_jobs,
        latest_snapshot_materialized_at_utc=(
            aggregate_row["latest_snapshot_materialized_at_utc"].isoformat()
            if aggregate_row["latest_snapshot_materialized_at_utc"] is not None
            else None
        ),
        latest_position_timeseries_materialized_at_utc=(
            aggregate_row["latest_position_timeseries_materialized_at_utc"].isoformat()
            if aggregate_row["latest_position_timeseries_materialized_at_utc"] is not None
            else None
        ),
        latest_portfolio_timeseries_materialized_at_utc=(
            aggregate_row["latest_portfolio_timeseries_materialized_at_utc"].isoformat()
            if aggregate_row["latest_portfolio_timeseries_materialized_at_utc"] is not None
            else None
        ),
        latest_valuation_job_updated_at_utc=(
            aggregate_row["latest_valuation_job_updated_at_utc"].isoformat()
            if aggregate_row["latest_valuation_job_updated_at_utc"] is not None
            else None
        ),
        latest_aggregation_job_updated_at_utc=(
            aggregate_row["latest_aggregation_job_updated_at_utc"].isoformat()
            if aggregate_row["latest_aggregation_job_updated_at_utc"] is not None
            else None
        ),
        completed_valuation_jobs_without_position_timeseries=int(
            aggregate_row["completed_valuation_jobs_without_position_timeseries"] or 0
        ),
        oldest_completed_valuation_without_position_timeseries_at_utc=(
            aggregate_row[
                "oldest_completed_valuation_without_position_timeseries_at_utc"
            ].isoformat()
            if aggregate_row["oldest_completed_valuation_without_position_timeseries_at_utc"]
            is not None
            else None
        ),
        valuation_to_position_timeseries_latency_sample_count=int(
            aggregate_row["valuation_to_position_timeseries_latency_sample_count"] or 0
        ),
        valuation_to_position_timeseries_latency_p50_seconds=(
            float(aggregate_row["valuation_to_position_timeseries_latency_p50_seconds"])
            if aggregate_row["valuation_to_position_timeseries_latency_p50_seconds"] is not None
            else None
        ),
        valuation_to_position_timeseries_latency_p95_seconds=(
            float(aggregate_row["valuation_to_position_timeseries_latency_p95_seconds"])
            if aggregate_row["valuation_to_position_timeseries_latency_p95_seconds"] is not None
            else None
        ),
        valuation_to_position_timeseries_latency_max_seconds=(
            float(aggregate_row["valuation_to_position_timeseries_latency_max_seconds"])
            if aggregate_row["valuation_to_position_timeseries_latency_max_seconds"] is not None
            else None
        ),
    )


def _probe_json(
    *,
    session: requests.Session,
    url: str,
    repetitions: int,
) -> tuple[int, list[float], Any]:
    payload: Any = None
    status_code = 0
    samples: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        response = session.get(url, timeout=60)
        samples.append(round((time.perf_counter() - started) * 1000, 3))
        status_code = response.status_code
        if response.status_code != 200:
            return status_code, samples, response.text[:500]
        payload = response.json()
    return status_code, samples, payload


def _run_sample_reconciliation(
    *,
    session: requests.Session,
    base_url: str,
    portfolio_id: str,
    business_date: str,
    epoch: int,
) -> tuple[bool, int]:
    response = session.post(
        f"{base_url}/reconciliation/runs/timeseries-integrity",
        json={
            "portfolio_id": portfolio_id,
            "business_date": business_date,
            "epoch": epoch,
        },
        timeout=120,
    )
    if response.status_code != 200:
        return False, -1
    body = response.json()
    findings = body.get("findings", [])
    return len(findings) == 0, len(findings)


def _collect_sample_portfolios(
    *,
    session: requests.Session,
    query_base_url: str,
    query_control_base_url: str,
    reconciliation_base_url: str,
    portfolios: list[dict[str, Any]],
    specs: list[InstrumentSpec],
    trade_date: str,
    sample_size: int,
    positions_probe_repetitions: int = 3,
    transactions_probe_repetitions: int = 3,
    support_probe_repetitions: int = 2,
) -> tuple[list[SamplePortfolioResult], list[ApiProbeResult]]:
    samples: list[SamplePortfolioResult] = []
    probes: list[ApiProbeResult] = []
    portfolio_ids = [portfolio["portfolio_id"] for portfolio in portfolios[:sample_size]]
    expected_value = expected_portfolio_market_value(specs)
    for portfolio_id in portfolio_ids:
        positions_url = (
            f"{query_base_url}/portfolios/{portfolio_id}/positions"
            f"?as_of_date={trade_date}"
        )
        tx_url = (
            f"{query_base_url}/portfolios/{portfolio_id}/transactions"
            f"?limit={len(specs)}&include_projected=true"
        )
        support_url = f"{query_control_base_url}/support/portfolios/{portfolio_id}/overview"
        positions_status, positions_samples, positions_payload = _probe_json(
            session=session,
            url=positions_url,
            repetitions=positions_probe_repetitions,
        )
        tx_status, tx_samples, tx_payload = _probe_json(
            session=session,
            url=tx_url,
            repetitions=transactions_probe_repetitions,
        )
        support_status, support_samples, support_payload = _probe_json(
            session=session,
            url=support_url,
            repetitions=support_probe_repetitions,
        )
        for endpoint, status, samples_ms, payload in (
            (positions_url, positions_status, positions_samples, positions_payload),
            (tx_url, tx_status, tx_samples, tx_payload),
            (support_url, support_status, support_samples, support_payload),
        ):
            probes.append(
                ApiProbeResult(
                    endpoint=endpoint,
                    status_code=status,
                    latency_ms_samples=samples_ms,
                    p95_ms=round(_percentile(samples_ms, 95), 3),
                    median_ms=round(statistics.median(samples_ms), 3),
                    check_passed=status == 200,
                    failure_detail=None if status == 200 else str(payload),
                )
            )
        positions = positions_payload.get("positions", []) if positions_status == 200 else []
        transactions = tx_payload.get("transactions", []) if tx_status == 200 else []
        support = support_payload if support_status == 200 else {}
        observed_total_value = Decimal("0")
        for position in positions:
            valuation = position.get("valuation") or {}
            observed_total_value += _parse_decimal(valuation.get("market_value", "0"))
        reconciliation_passed, finding_count = _run_sample_reconciliation(
            session=session,
            base_url=reconciliation_base_url,
            portfolio_id=portfolio_id,
            business_date=str(support.get("business_date", trade_date)),
            epoch=int(support.get("current_epoch", 0) or 0),
        )
        samples.append(
            SamplePortfolioResult(
                portfolio_id=portfolio_id,
                positions_count=len(positions),
                transactions_count=len(transactions),
                support_publish_allowed=bool(support.get("publish_allowed", False)),
                support_pending_valuation_jobs=int(support.get("pending_valuation_jobs", 0)),
                support_pending_aggregation_jobs=int(
                    support.get("pending_aggregation_jobs", 0)
                ),
                support_latest_booked_position_snapshot_date=support.get(
                    "latest_booked_position_snapshot_date"
                ),
                total_market_value=_decimal_str(observed_total_value),
                expected_market_value=_decimal_str(expected_value),
                reconciliation_passed=reconciliation_passed,
                reconciliation_finding_count=finding_count,
            )
        )
    return samples, probes


def _collect_log_evidence(*, started_at: str) -> list[LogEvidence]:
    evidence: list[LogEvidence] = []
    for container_name in LOG_SERVICE_CONTAINERS:
        completed = subprocess.run(
            ["docker", "logs", "--since", started_at, container_name],
            check=False,
            capture_output=True,
            text=True,
        )
        combined = f"{completed.stdout}\n{completed.stderr}"
        error_lines: list[str] = []
        for raw_line in combined.splitlines():
            line = raw_line.strip()
            lower_line = line.lower()
            if "traceback" in lower_line:
                error_lines.append(line)
                continue
            if '"level": "ERROR"' in line or '"level":"ERROR"' in line:
                error_lines.append(line)
                continue
            if lower_line.startswith("error:") or lower_line.startswith("[error]"):
                error_lines.append(line)
        evidence.append(
            LogEvidence(
                container_name=container_name,
                error_line_count=len(error_lines),
                sample_error_lines=error_lines[:5],
            )
        )
    return evidence


def _evaluate_report(report: ScenarioReport) -> list[str]:
    failures: list[str] = []
    if report.terminal_status != "complete":
        failures.append(f"scenario terminal_status is {report.terminal_status}")
    tie_out = report.database_tie_out
    if tie_out.portfolios_count != int(report.config["portfolio_count"]):
        failures.append(
            "portfolio_count "
            f"{tie_out.portfolios_count} != expected {report.config['portfolio_count']}"
        )
    if tie_out.transactions_count != int(report.config["transaction_count"]):
        failures.append(
            "transactions_count "
            f"{tie_out.transactions_count} != expected {report.config['transaction_count']}"
        )
    if tie_out.portfolios_with_snapshots != int(report.config["portfolio_count"]):
        failures.append(
            "portfolios_with_snapshots "
            f"{tie_out.portfolios_with_snapshots} != expected {report.config['portfolio_count']}"
        )
    if tie_out.complete_portfolios != int(report.config["portfolio_count"]):
        failures.append(
            "complete_portfolios "
            f"{tie_out.complete_portfolios} != expected {report.config['portfolio_count']}"
        )
    if tie_out.incomplete_portfolios != 0:
        failures.append(f"incomplete_portfolios {tie_out.incomplete_portfolios} != 0")
    if tie_out.portfolios_waiting_for_snapshots != 0:
        failures.append(
            "portfolios_waiting_for_snapshots "
            f"{tie_out.portfolios_waiting_for_snapshots} != 0"
        )
    if tie_out.snapshots_count != int(report.config["transaction_count"]):
        failures.append(
            "snapshots_count "
            f"{tie_out.snapshots_count} != expected {report.config['transaction_count']}"
        )
    if tie_out.snapshot_portfolios_without_position_timeseries != 0:
        failures.append(
            "snapshot_portfolios_without_position_timeseries "
            f"{tie_out.snapshot_portfolios_without_position_timeseries} != 0"
        )
    if tie_out.portfolios_with_position_timeseries != int(report.config["portfolio_count"]):
        failures.append(
            "portfolios_with_position_timeseries "
            f"{tie_out.portfolios_with_position_timeseries} != expected "
            f"{report.config['portfolio_count']}"
        )
    if tie_out.position_timeseries_count != int(report.config["transaction_count"]):
        failures.append(
            "position_timeseries_count "
            f"{tie_out.position_timeseries_count} != expected {report.config['transaction_count']}"
        )
    if tie_out.portfolios_waiting_for_position_timeseries != 0:
        failures.append(
            "portfolios_waiting_for_position_timeseries "
            f"{tie_out.portfolios_waiting_for_position_timeseries} != 0"
        )
    if tie_out.portfolios_with_portfolio_timeseries != int(report.config["portfolio_count"]):
        failures.append(
            "portfolios_with_portfolio_timeseries "
            f"{tie_out.portfolios_with_portfolio_timeseries} != expected "
            f"{report.config['portfolio_count']}"
        )
    if tie_out.position_timeseries_portfolios_without_portfolio_timeseries != 0:
        failures.append(
            "position_timeseries_portfolios_without_portfolio_timeseries "
            f"{tie_out.position_timeseries_portfolios_without_portfolio_timeseries} != 0"
        )
    if tie_out.portfolio_timeseries_count != int(report.config["portfolio_count"]):
        failures.append(
            "portfolio_timeseries_count "
            f"{tie_out.portfolio_timeseries_count} != expected {report.config['portfolio_count']}"
        )
    if tie_out.portfolios_waiting_for_portfolio_timeseries != 0:
        failures.append(
            "portfolios_waiting_for_portfolio_timeseries "
            f"{tie_out.portfolios_waiting_for_portfolio_timeseries} != 0"
        )
    if tie_out.summed_snapshot_quantity != tie_out.expected_total_quantity:
        failures.append(
            "summed_snapshot_quantity "
            f"{tie_out.summed_snapshot_quantity} != expected {tie_out.expected_total_quantity}"
        )
    if tie_out.summed_snapshot_market_value != tie_out.expected_total_market_value:
        failures.append(
            "summed_snapshot_market_value "
            f"{tie_out.summed_snapshot_market_value} != expected "
            f"{tie_out.expected_total_market_value}"
        )
    expected_security_quantity = _decimal_str(Decimal(str(report.config["portfolio_count"])))
    if tie_out.per_security_quantity_min != expected_security_quantity:
        failures.append(
            "per_security_quantity_min "
            f"{tie_out.per_security_quantity_min} != expected {expected_security_quantity}"
        )
    if tie_out.per_security_quantity_max != expected_security_quantity:
        failures.append(
            "per_security_quantity_max "
            f"{tie_out.per_security_quantity_max} != expected {expected_security_quantity}"
        )
    if tie_out.open_valuation_jobs != 0:
        failures.append(f"open_valuation_jobs {tie_out.open_valuation_jobs} != 0")
    if tie_out.open_aggregation_jobs != 0:
        failures.append(f"open_aggregation_jobs {tie_out.open_aggregation_jobs} != 0")
    for sample in report.sample_portfolios:
        expected_positions = int(report.config["transactions_per_portfolio"])
        if sample.positions_count != expected_positions:
            failures.append(
                f"{sample.portfolio_id} positions_count {sample.positions_count} != expected "
                f"{expected_positions}"
            )
        if sample.transactions_count != expected_positions:
            failures.append(
                f"{sample.portfolio_id} transactions_count {sample.transactions_count} != expected "
                f"{expected_positions}"
            )
        if sample.total_market_value != sample.expected_market_value:
            failures.append(
                f"{sample.portfolio_id} total_market_value {sample.total_market_value} != expected "
                f"{sample.expected_market_value}"
            )
        if not sample.reconciliation_passed:
            failures.append(
                f"{sample.portfolio_id} reconciliation "
                f"findings={sample.reconciliation_finding_count}"
            )
    for probe in report.api_probes:
        if not probe.check_passed:
            failures.append(
                f"API probe failed {probe.endpoint} status={probe.status_code}: "
                f"{probe.failure_detail}"
            )
    for log in report.log_evidence:
        if log.error_line_count > 0:
            failures.append(
                f"{log.container_name} logged {log.error_line_count} error/traceback lines"
            )
    return failures


def _write_report(*, report: ScenarioReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report.run_id}-bank-day-load.json"
    md_path = output_dir / f"{report.run_id}-bank-day-load.md"
    json_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    markdown = [
        f"# Bank-Day Load Scenario {report.run_id}",
        "",
        f"- Terminal status: {report.terminal_status}",
        f"- Started: {report.started_at}",
        f"- Ended: {report.ended_at}",
        f"- Duration seconds: {report.duration_seconds}",
        f"- Checks passed: {report.checks_passed}",
        f"- Failures: {len(report.failures)}",
        "",
        "## Config",
        "",
        "```json",
        json.dumps(report.config, indent=2),
        "```",
        "",
        "## Ingestion Phases",
        "",
    ]
    for phase in report.ingest_phases:
        markdown.append(
            f"- `{phase.endpoint}` records={phase.record_count} batches={phase.batch_count} "
            f"duration_s={phase.duration_seconds}"
        )
    markdown.extend(
        [
            "",
            "## Pipeline Health",
            "",
            f"- Drain seconds: {report.drain_seconds}",
            f"- Peak backlog jobs: {report.peak_backlog_jobs}",
            f"- Peak backlog age seconds: {report.peak_backlog_age_seconds}",
            f"- Peak replay pressure ratio: {report.peak_replay_pressure_ratio}",
            f"- Peak DLQ events in window: {report.peak_dlq_events_in_window}",
            "",
            "## Database Tie-Out",
            "",
            "```json",
            json.dumps(asdict(report.database_tie_out), indent=2),
            "```",
            "",
            "## Sample Portfolios",
            "",
            "```json",
            json.dumps([asdict(item) for item in report.sample_portfolios], indent=2),
            "```",
            "",
            "## API Probes",
            "",
            "```json",
            json.dumps([asdict(item) for item in report.api_probes], indent=2),
            "```",
            "",
            "## Log Evidence",
            "",
            "```json",
            json.dumps([asdict(item) for item in report.log_evidence], indent=2),
            "```",
            "",
            "## Failures",
            "",
        ]
    )
    markdown.extend([f"- {failure}" for failure in report.failures] or ["- none"])
    md_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return json_path, md_path


def _zero_tie_out(*, portfolio_count: int, specs: list[InstrumentSpec]) -> DatabaseTieOut:
    return DatabaseTieOut(
        portfolios_count=0,
        instruments_count=0,
        transactions_count=0,
        portfolios_with_snapshots=0,
        snapshots_count=0,
        portfolios_with_position_timeseries=0,
        complete_portfolios=0,
        incomplete_portfolios=portfolio_count,
        portfolios_waiting_for_snapshots=portfolio_count,
        snapshot_portfolios_without_position_timeseries=0,
        position_timeseries_count=0,
        portfolios_with_portfolio_timeseries=0,
        portfolios_waiting_for_position_timeseries=0,
        position_timeseries_portfolios_without_portfolio_timeseries=0,
        portfolios_waiting_for_portfolio_timeseries=0,
        portfolio_timeseries_count=0,
        summed_snapshot_quantity="0.0000000000",
        expected_total_quantity=_decimal_str(Decimal(portfolio_count * len(specs))),
        summed_snapshot_market_value="0.0000000000",
        expected_total_market_value=_decimal_str(
            expected_total_market_value(portfolio_count=portfolio_count, specs=specs)
        ),
        per_security_quantity_min=None,
        per_security_quantity_max=None,
        pending_valuation_jobs=0,
        processing_valuation_jobs=0,
        open_valuation_jobs=0,
        pending_aggregation_jobs=0,
        processing_aggregation_jobs=0,
        open_aggregation_jobs=0,
        latest_snapshot_materialized_at_utc=None,
        latest_position_timeseries_materialized_at_utc=None,
        latest_portfolio_timeseries_materialized_at_utc=None,
        latest_valuation_job_updated_at_utc=None,
        latest_aggregation_job_updated_at_utc=None,
        completed_valuation_jobs_without_position_timeseries=0,
        oldest_completed_valuation_without_position_timeseries_at_utc=None,
        valuation_to_position_timeseries_latency_sample_count=0,
        valuation_to_position_timeseries_latency_p50_seconds=None,
        valuation_to_position_timeseries_latency_p95_seconds=None,
        valuation_to_position_timeseries_latency_max_seconds=None,
    )


def _safe_build_database_tie_out(
    *,
    engine: Any,
    run_id: str,
    trade_date: str,
    portfolio_count: int,
    specs: list[InstrumentSpec],
) -> tuple[DatabaseTieOut, list[str]]:
    try:
        return (
            _build_database_tie_out(
                engine=engine,
                run_id=run_id,
                trade_date=trade_date,
                portfolio_count=portfolio_count,
                specs=specs,
            ),
            [],
        )
    except Exception as exc:
        return (
            _zero_tie_out(portfolio_count=portfolio_count, specs=specs),
            [f"failed to collect database tie-out for partial report: {exc}"],
        )


def _safe_collect_sample_portfolios(
    *,
    session: requests.Session,
    query_base_url: str,
    query_control_base_url: str,
    reconciliation_base_url: str,
    portfolios: list[dict[str, Any]],
    specs: list[InstrumentSpec],
    trade_date: str,
    sample_size: int,
) -> tuple[list[SamplePortfolioResult], list[ApiProbeResult], list[str]]:
    try:
        samples, probes = _collect_sample_portfolios(
            session=session,
            query_base_url=query_base_url,
            query_control_base_url=query_control_base_url,
            reconciliation_base_url=reconciliation_base_url,
            portfolios=portfolios,
            specs=specs,
            trade_date=trade_date,
            sample_size=sample_size,
        )
        return samples, probes, []
    except Exception as exc:
        return [], [], [f"failed to collect sample portfolio evidence for partial report: {exc}"]


def _safe_collect_log_evidence(*, started_at: str) -> tuple[list[LogEvidence], list[str]]:
    try:
        return _collect_log_evidence(started_at=started_at), []
    except Exception as exc:
        return [], [f"failed to collect log evidence for partial report: {exc}"]


def _build_config(args: argparse.Namespace, *, resolved_trade_date: str) -> dict[str, Any]:
    return {
        "portfolio_count": args.portfolio_count,
        "transactions_per_portfolio": args.transactions_per_portfolio,
        "transaction_count": args.portfolio_count * args.transactions_per_portfolio,
        "transaction_batch_size": args.transaction_batch_size,
        "max_records_per_minute": args.max_records_per_minute,
        "max_requests_per_minute": args.max_requests_per_minute,
        "trade_date": resolved_trade_date,
        "host_database_url": args.host_database_url,
        "ingestion_base_url": args.ingestion_base_url,
        "query_base_url": args.query_base_url,
        "query_control_base_url": args.query_control_base_url,
        "event_replay_base_url": args.event_replay_base_url,
        "reconciliation_base_url": args.reconciliation_base_url,
    }


def _finalize_report(
    *,
    args: argparse.Namespace,
    run_id: str,
    terminal_status: str,
    started_at: str,
    started_monotonic: float,
    resolved_trade_date: str,
    ingest_phases: list[IngestPhaseResult],
    drain_seconds: float,
    health_samples: list[HealthSample],
    tie_out: DatabaseTieOut,
    sample_portfolios: list[SamplePortfolioResult],
    api_probes: list[ApiProbeResult],
    log_evidence: list[LogEvidence],
    initial_failures: list[str],
) -> ScenarioReport:
    report_base = ScenarioReport(
        scenario_name=args.scenario_name,
        run_id=run_id,
        terminal_status=terminal_status,
        started_at=started_at,
        ended_at=_utc_now(),
        duration_seconds=round(time.perf_counter() - started_monotonic, 3),
        config=_build_config(args, resolved_trade_date=resolved_trade_date),
        ingest_phases=ingest_phases,
        drain_seconds=drain_seconds,
        peak_backlog_jobs=max((sample.backlog_jobs for sample in health_samples), default=0),
        peak_backlog_age_seconds=max(
            (sample.backlog_age_seconds for sample in health_samples),
            default=0.0,
        ),
        peak_replay_pressure_ratio=max(
            (sample.replay_pressure_ratio for sample in health_samples),
            default=0.0,
        ),
        peak_dlq_events_in_window=max(
            (sample.dlq_events_in_window for sample in health_samples),
            default=0,
        ),
        health_samples=health_samples,
        database_tie_out=tie_out,
        sample_portfolios=sample_portfolios,
        api_probes=api_probes,
        log_evidence=log_evidence,
        checks_passed=False,
        failures=[],
    )
    failures = initial_failures + _evaluate_report(report_base)
    return ScenarioReport(
        scenario_name=report_base.scenario_name,
        run_id=report_base.run_id,
        terminal_status=report_base.terminal_status,
        started_at=report_base.started_at,
        ended_at=report_base.ended_at,
        duration_seconds=report_base.duration_seconds,
        config=report_base.config,
        ingest_phases=report_base.ingest_phases,
        drain_seconds=report_base.drain_seconds,
        peak_backlog_jobs=report_base.peak_backlog_jobs,
        peak_backlog_age_seconds=report_base.peak_backlog_age_seconds,
        peak_replay_pressure_ratio=report_base.peak_replay_pressure_ratio,
        peak_dlq_events_in_window=report_base.peak_dlq_events_in_window,
        health_samples=report_base.health_samples,
        database_tie_out=report_base.database_tie_out,
        sample_portfolios=report_base.sample_portfolios,
        api_probes=report_base.api_probes,
        log_evidence=report_base.log_evidence,
        checks_passed=len(failures) == 0,
        failures=failures,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-name", default="bank-day-average-load")
    parser.add_argument("--portfolio-count", type=int, default=1000)
    parser.add_argument("--transactions-per-portfolio", type=int, default=100)
    parser.add_argument("--transaction-batch-size", type=int, default=2000)
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--ingestion-base-url", default=DEFAULT_INGESTION_BASE_URL)
    parser.add_argument("--query-base-url", default=DEFAULT_QUERY_BASE_URL)
    parser.add_argument("--query-control-base-url", default=DEFAULT_QUERY_CONTROL_BASE_URL)
    parser.add_argument("--event-replay-base-url", default=DEFAULT_EVENT_REPLAY_BASE_URL)
    parser.add_argument("--reconciliation-base-url", default=DEFAULT_RECONCILIATION_BASE_URL)
    parser.add_argument("--host-database-url", default=DEFAULT_HOST_DATABASE_URL)
    parser.add_argument("--ops-token", default=DEFAULT_OPS_TOKEN)
    parser.add_argument("--readiness-timeout-seconds", type=int, default=180)
    parser.add_argument("--drain-timeout-seconds", type=int, default=3600)
    parser.add_argument("--health-poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--max-records-per-minute", type=int, default=45000)
    parser.add_argument("--max-requests-per-minute", type=int, default=450)
    parser.add_argument("--rate-limit-sleep-seconds", type=int, default=60)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if args.transactions_per_portfolio <= 0:
        raise ValueError("transactions_per_portfolio must be positive.")
    if args.sample_size <= 0:
        raise ValueError("sample_size must be positive.")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    started_at = _utc_now()
    os.environ["HOST_DATABASE_URL"] = args.host_database_url
    engine = create_engine(get_sync_database_url(), future=True)
    resolved_trade_date = _resolve_trade_date(
        engine=engine,
        explicit_trade_date=args.trade_date,
    )
    _wait_ready(
        base_urls=[
            args.ingestion_base_url,
            args.query_base_url,
            args.query_control_base_url,
            args.event_replay_base_url,
            args.reconciliation_base_url,
        ],
        timeout_seconds=args.readiness_timeout_seconds,
    )

    portfolios = _build_portfolios(
        run_id=run_id,
        portfolio_count=args.portfolio_count,
        trade_date=resolved_trade_date,
    )
    specs = _build_instrument_specs(
        run_id=run_id,
        instrument_count=args.transactions_per_portfolio,
    )
    session = requests.Session()
    ingest_phases: list[IngestPhaseResult] = []
    portfolio_pattern = {"portfolio_pattern": f"LOAD_{run_id}_PF_%"}
    security_pattern = {"security_pattern": f"LOAD_{run_id}_SEC_%"}
    health_monitor = HealthMonitor(
        event_replay_base_url=args.event_replay_base_url,
        ops_token=args.ops_token,
        interval_seconds=args.health_poll_interval_seconds,
    )
    started_monotonic = time.perf_counter()
    terminal_status = "failed"
    partial_failures: list[str] = []

    def _request_interrupt(signum: int, _frame: Any) -> None:
        signal_name = signal.Signals(signum).name
        raise ScenarioInterrupted(f"received {signal_name}")

    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _request_interrupt)
    signal.signal(signal.SIGTERM, _request_interrupt)
    health_monitor.start()
    try:
        ingest_phases.append(
            _ingest_static_payload(
                session=session,
                base_url=args.ingestion_base_url,
                endpoint="/ingest/business-dates",
                root_key="business_dates",
                rows=[{"business_date": resolved_trade_date}],
            )
        )
        ingest_phases.append(
            _ingest_static_payload(
                session=session,
                base_url=args.ingestion_base_url,
                endpoint="/ingest/portfolios",
                root_key="portfolios",
                rows=portfolios,
            )
        )
        _wait_for_seed_materialization(
            engine=engine,
            sql="""
            SELECT count(*) AS count
            FROM portfolios
            WHERE portfolio_id LIKE :portfolio_pattern
            """,
            params=portfolio_pattern,
            expected_count=args.portfolio_count,
            label="portfolio seed",
            timeout_seconds=args.readiness_timeout_seconds,
        )
        ingest_phases.append(
            _ingest_static_payload(
                session=session,
                base_url=args.ingestion_base_url,
                endpoint="/ingest/instruments",
                root_key="instruments",
                rows=_build_instruments_payload(specs),
            )
        )
        _wait_for_seed_materialization(
            engine=engine,
            sql="""
            SELECT count(*) AS count
            FROM instruments
            WHERE security_id LIKE :security_pattern
            """,
            params=security_pattern,
            expected_count=args.transactions_per_portfolio,
            label="instrument seed",
            timeout_seconds=args.readiness_timeout_seconds,
        )
        ingest_phases.append(
            _ingest_static_payload(
                session=session,
                base_url=args.ingestion_base_url,
                endpoint="/ingest/fx-rates",
                root_key="fx_rates",
                rows=_build_fx_rates_payload(
                    currencies=SUPPORTED_CURRENCIES,
                    rate_date=resolved_trade_date,
                ),
            )
        )
        _wait_for_seed_materialization(
            engine=engine,
            sql="""
            SELECT count(*) AS count
            FROM fx_rates
            WHERE rate_date = :trade_date
              AND from_currency IN ('USD', 'EUR', 'SGD', 'GBP')
              AND to_currency IN ('USD', 'EUR', 'SGD', 'GBP')
            """,
            params={"trade_date": resolved_trade_date},
            expected_count=len(SUPPORTED_CURRENCIES) * (len(SUPPORTED_CURRENCIES) - 1),
            label="fx seed",
            timeout_seconds=args.readiness_timeout_seconds,
        )
        ingest_phases.append(
            _ingest_static_payload(
                session=session,
                base_url=args.ingestion_base_url,
                endpoint="/ingest/market-prices",
                root_key="market_prices",
                rows=_build_market_prices_payload(
                    specs=specs,
                    price_date=resolved_trade_date,
                ),
            )
        )
        _wait_for_seed_materialization(
            engine=engine,
            sql="""
            SELECT count(*) AS count
            FROM market_prices
            WHERE security_id LIKE :security_pattern
              AND price_date = :trade_date
            """,
            params={
                "security_pattern": security_pattern["security_pattern"],
                "trade_date": resolved_trade_date,
            },
            expected_count=args.transactions_per_portfolio,
            label="market price seed",
            timeout_seconds=args.readiness_timeout_seconds,
        )
        ingest_phases.append(
            _ingest_transaction_batches(
                session=session,
                base_url=args.ingestion_base_url,
                batches=iter_transaction_batches(
                    run_id=run_id,
                    portfolios=portfolios,
                    specs=specs,
                    trade_date=resolved_trade_date,
                    transaction_batch_size=args.transaction_batch_size,
                ),
                max_records_per_minute=args.max_records_per_minute,
                max_requests_per_minute=args.max_requests_per_minute,
                rate_limit_sleep_seconds=args.rate_limit_sleep_seconds,
            )
        )
        drain_seconds = _wait_for_cycle_completion(
            engine=engine,
            run_id=run_id,
            trade_date=resolved_trade_date,
            portfolio_count=args.portfolio_count,
            transaction_count=args.portfolio_count * args.transactions_per_portfolio,
            timeout_seconds=args.drain_timeout_seconds,
        )
        terminal_status = "complete"
    except (ScenarioInterrupted, KeyboardInterrupt) as exc:
        partial_failures.append(str(exc))
        terminal_status = "aborted"
    except Exception as exc:
        partial_failures.append(str(exc))
        terminal_status = "failed"
    finally:
        health_monitor.stop()
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)

    drain_seconds = locals().get("drain_seconds", 0.0)
    sample_portfolios, api_probes, sample_failures = _safe_collect_sample_portfolios(
        session=session,
        query_base_url=args.query_base_url,
        query_control_base_url=args.query_control_base_url,
        reconciliation_base_url=args.reconciliation_base_url,
        portfolios=portfolios,
        specs=specs,
        trade_date=resolved_trade_date,
        sample_size=min(args.sample_size, len(portfolios)),
    )
    tie_out, tie_out_failures = _safe_build_database_tie_out(
        engine=engine,
        run_id=run_id,
        trade_date=resolved_trade_date,
        portfolio_count=args.portfolio_count,
        specs=specs,
    )
    log_evidence, log_failures = _safe_collect_log_evidence(started_at=started_at)
    report = _finalize_report(
        args=args,
        run_id=run_id,
        terminal_status=terminal_status,
        started_at=started_at,
        started_monotonic=started_monotonic,
        resolved_trade_date=resolved_trade_date,
        ingest_phases=ingest_phases,
        drain_seconds=drain_seconds,
        health_samples=health_monitor.samples,
        tie_out=tie_out,
        sample_portfolios=sample_portfolios,
        api_probes=api_probes,
        log_evidence=log_evidence,
        initial_failures=partial_failures + sample_failures + tie_out_failures + log_failures,
    )
    json_path, md_path = _write_report(report=report, output_dir=Path(args.output_dir))
    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote Markdown report: {md_path}")
    if report.failures:
        for failure in report.failures:
            print(f"FAILURE: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
