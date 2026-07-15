"""Model and verify effective-dated market-price correction workloads."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
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
          AND valuation_date = :trade_date
          AND status = 'COMPLETE'
          AND updated_at >= :correction_started_at
    ) AS corrected_valuation_jobs,
    (
        SELECT count(*)
        FROM position_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date = :trade_date
          AND updated_at >= :correction_started_at
    ) AS corrected_position_timeseries,
    (
        SELECT count(*)
        FROM portfolio_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date = :trade_date
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
    ) AS failed_aggregation_jobs
FROM daily_position_snapshots snapshot
WHERE snapshot.portfolio_id LIKE :portfolio_pattern
  AND snapshot.date = :trade_date
"""


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
    trade_date: str,
    portfolio_count: int,
    transaction_count: int,
    expected_market_value: Decimal,
    correction_started_at: datetime,
    timeout_seconds: int,
) -> float:
    """Wait until every affected derived row reflects one accepted correction."""

    started = time.perf_counter()
    deadline = time.time() + timeout_seconds
    params = {
        "portfolio_pattern": f"LOAD_{run_id}_PF_%",
        "trade_date": trade_date,
        "correction_started_at": correction_started_at,
    }
    while time.time() < deadline:
        row = row_reader(_CORRECTED_DERIVED_STATE_SQL, params)
        if int(row["failed_valuation_jobs"]) > 0 or int(row["failed_aggregation_jobs"]) > 0:
            raise RuntimeError(
                "Price correction entered FAILED state before drain: "
                f"failed_valuation_jobs={row['failed_valuation_jobs']} "
                f"failed_aggregation_jobs={row['failed_aggregation_jobs']}"
            )
        if (
            int(row["corrected_snapshots"]) == transaction_count
            and Decimal(str(row["corrected_market_value"])) == expected_market_value
            and int(row["corrected_valuation_jobs"]) == transaction_count
            and int(row["corrected_position_timeseries"]) == transaction_count
            and int(row["corrected_portfolio_timeseries"]) == portfolio_count
            and int(row["open_valuation_jobs"]) == 0
            and int(row["open_aggregation_jobs"]) == 0
        ):
            return round(time.perf_counter() - started, 3)
        time.sleep(5)
    raise TimeoutError("Market price correction did not fully rematerialize before timeout.")
