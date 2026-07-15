"""Model and verify effective-dated market-price correction workloads."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class SyntheticInstrumentSpec:
    """Describe one deterministic instrument used by a managed workload."""

    security_id: str
    currency: str
    trade_price: Decimal
    market_price: Decimal


RowReader = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class DerivedStateCorrectionEvidence:
    """Record exact expected and observed correction materialization facts."""

    correction_started_at: str
    window_start_date: str
    window_end_date: str
    business_date_count: int
    drain_seconds: float
    expected_snapshots: int
    corrected_snapshots: int
    expected_valuation_jobs: int
    corrected_valuation_jobs: int
    expected_position_timeseries: int
    corrected_position_timeseries: int
    expected_portfolio_timeseries: int
    corrected_portfolio_timeseries: int
    expected_window_market_value: str
    corrected_window_market_value: str


_CORRECTED_DERIVED_STATE_SQL = """
SELECT
    count(*) FILTER (
        WHERE snapshot.updated_at >= :correction_started_at
    ) AS corrected_snapshots,
    coalesce(sum(snapshot.market_value), 0) AS corrected_market_value,
    (
        SELECT count(*)
        FROM portfolio_valuation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND valuation_date BETWEEN :window_start_date AND :window_end_date
          AND status = 'COMPLETE'
          AND updated_at >= :correction_started_at
    ) AS corrected_valuation_jobs,
    (
        SELECT count(*)
        FROM position_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date BETWEEN :window_start_date AND :window_end_date
          AND updated_at >= :correction_started_at
    ) AS corrected_position_timeseries,
    (
        SELECT count(*)
        FROM portfolio_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date BETWEEN :window_start_date AND :window_end_date
          AND updated_at >= :correction_started_at
    ) AS corrected_portfolio_timeseries,
    (
        SELECT count(*)
        FROM portfolio_valuation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND status IN ('PENDING', 'PROCESSING')
    ) AS open_valuation_jobs,
    (
        SELECT count(*)
        FROM portfolio_aggregation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND status IN ('PENDING', 'PROCESSING')
    ) AS open_aggregation_jobs,
    (
        SELECT count(*)
        FROM portfolio_valuation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND status = 'FAILED'
    ) AS failed_valuation_jobs,
    (
        SELECT count(*)
        FROM portfolio_aggregation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND status = 'FAILED'
    ) AS failed_aggregation_jobs,
    (
        SELECT count(*)
        FROM outbox_events
        WHERE status = 'PENDING'
    ) AS pending_outbox_events,
    (
        SELECT count(*)
        FROM outbox_events
        WHERE status = 'FAILED'
    ) AS failed_outbox_events
FROM daily_position_snapshots snapshot
WHERE snapshot.portfolio_id LIKE :portfolio_pattern
  AND snapshot.date BETWEEN :window_start_date AND :window_end_date
"""


def build_synthetic_business_date_window(
    *,
    as_of_date: str,
    business_date_count: int,
) -> tuple[str, ...]:
    """Build an inclusive weekday window for an explicitly seeded test calendar."""

    if business_date_count <= 0:
        raise ValueError("business_date_count must be positive")
    current_date = date.fromisoformat(as_of_date)
    if current_date.weekday() >= 5:
        raise ValueError("as_of_date must be a weekday in the synthetic business calendar")

    business_dates: list[str] = []
    while len(business_dates) < business_date_count:
        if current_date.weekday() < 5:
            business_dates.append(current_date.isoformat())
        current_date -= timedelta(days=1)
    return tuple(reversed(business_dates))


def apply_market_price_correction(
    *,
    specs: list[SyntheticInstrumentSpec],
    multiplier: Decimal,
) -> list[SyntheticInstrumentSpec]:
    """Return corrected instrument facts using the ingestion contract's price precision."""

    if multiplier <= 0 or multiplier == 1:
        raise ValueError("market price correction multiplier must be positive and not equal to 1")
    return [
        replace(
            spec,
            market_price=(spec.market_price * multiplier).quantize(Decimal("0.01")),
        )
        for spec in specs
    ]


def wait_for_corrected_derived_state(
    *,
    row_reader: RowReader,
    run_id: str,
    window_start_date: str,
    window_end_date: str,
    business_date_count: int,
    portfolio_count: int,
    transaction_count: int,
    expected_daily_market_value: Decimal,
    correction_started_at: datetime,
    timeout_seconds: int,
) -> DerivedStateCorrectionEvidence:
    """Wait until every affected derived row reflects one accepted correction."""

    started = time.perf_counter()
    deadline = time.time() + timeout_seconds
    if business_date_count <= 0:
        raise ValueError("business_date_count must be positive")
    if date.fromisoformat(window_start_date) > date.fromisoformat(window_end_date):
        raise ValueError("window_start_date must not be after window_end_date")
    expected_position_rows = transaction_count * business_date_count
    expected_portfolio_rows = portfolio_count * business_date_count
    expected_window_market_value = expected_daily_market_value * business_date_count
    params = {
        "portfolio_pattern": f"LOAD_{run_id}_PF_%",
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
        "correction_started_at": correction_started_at,
    }
    while time.time() < deadline:
        row = row_reader(_CORRECTED_DERIVED_STATE_SQL, params)
        if (
            int(row["failed_valuation_jobs"]) > 0
            or int(row["failed_aggregation_jobs"]) > 0
            or int(row["failed_outbox_events"]) > 0
        ):
            raise RuntimeError(
                "Price correction entered FAILED state before drain: "
                f"failed_valuation_jobs={row['failed_valuation_jobs']} "
                f"failed_aggregation_jobs={row['failed_aggregation_jobs']} "
                f"failed_outbox_events={row['failed_outbox_events']}"
            )
        if (
            int(row["corrected_snapshots"]) == expected_position_rows
            and Decimal(str(row["corrected_market_value"])) == expected_window_market_value
            and int(row["corrected_valuation_jobs"]) == expected_position_rows
            and int(row["corrected_position_timeseries"]) == expected_position_rows
            and int(row["corrected_portfolio_timeseries"]) == expected_portfolio_rows
            and int(row["open_valuation_jobs"]) == 0
            and int(row["open_aggregation_jobs"]) == 0
            and int(row["pending_outbox_events"]) == 0
        ):
            corrected_market_value = Decimal(str(row["corrected_market_value"]))
            return DerivedStateCorrectionEvidence(
                correction_started_at=correction_started_at.isoformat(),
                window_start_date=window_start_date,
                window_end_date=window_end_date,
                business_date_count=business_date_count,
                drain_seconds=round(time.perf_counter() - started, 3),
                expected_snapshots=expected_position_rows,
                corrected_snapshots=int(row["corrected_snapshots"]),
                expected_valuation_jobs=expected_position_rows,
                corrected_valuation_jobs=int(row["corrected_valuation_jobs"]),
                expected_position_timeseries=expected_position_rows,
                corrected_position_timeseries=int(row["corrected_position_timeseries"]),
                expected_portfolio_timeseries=expected_portfolio_rows,
                corrected_portfolio_timeseries=int(row["corrected_portfolio_timeseries"]),
                expected_window_market_value=f"{expected_window_market_value:.10f}",
                corrected_window_market_value=f"{corrected_market_value:.10f}",
            )
        time.sleep(5)
    raise TimeoutError("Market price correction did not fully rematerialize before timeout.")
