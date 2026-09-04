"""Model and verify effective-dated direct-pair FX correction workloads."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from scripts.operations.performance.market_price_correction import SyntheticInstrumentSpec

RowReader = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
MONEY_QUANTUM = Decimal("0.0000000001")
RATE_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class FxValuationExpectations:
    """Independent expected values for one direct-pair correction."""

    affected_instrument_count: int
    daily_affected_market_value: Decimal
    daily_total_market_value: Decimal
    daily_affected_unrealized_price: Decimal
    daily_affected_unrealized_fx: Decimal
    daily_affected_unrealized_total: Decimal


@dataclass(frozen=True, slots=True)
class FxMissingRateFailureEvidence:
    """Record fail-closed authority before an exact-date FX fact arrives."""

    observed_at: str
    from_currency: str
    to_currency: str
    valuation_date: str
    expected_affected_positions: int
    durable_affected_position_histories: int
    failed_valuation_jobs: int
    failed_snapshots_without_market_values: int
    affected_position_timeseries: int
    affected_portfolio_timeseries: int
    expected_unaffected_snapshots: int
    unaffected_current_snapshots: int


@dataclass(frozen=True, slots=True)
class FxDerivedStateCorrectionEvidence:
    """Record exact observed materialization facts for one FX correction."""

    correction_started_at: str
    from_currency: str
    to_currency: str
    effective_date: str
    window_start_date: str
    window_end_date: str
    business_date_count: int
    drain_seconds: float
    initial_rate: str
    corrected_rate: str
    expected_affected_snapshots: int
    corrected_affected_snapshots: int
    expected_valuation_jobs: int
    corrected_valuation_jobs: int
    expected_position_timeseries: int
    corrected_position_timeseries: int
    expected_portfolio_timeseries: int
    corrected_portfolio_timeseries: int
    processed_observations: int
    completed_pair_replay_jobs: int
    expected_affected_market_value: str
    corrected_affected_market_value: str
    expected_total_market_value: str
    corrected_total_market_value: str
    expected_unrealized_price: str
    corrected_unrealized_price: str
    expected_unrealized_fx: str
    corrected_unrealized_fx: str
    expected_unrealized_total: str
    corrected_unrealized_total: str
    unexpected_prior_affected_snapshot_updates: int


_FX_MISSING_RATE_FAILURE_SQL = """
WITH affected_histories AS (
    SELECT DISTINCT history.portfolio_id, history.security_id, history.epoch
    FROM position_history history
    JOIN instruments instrument
      ON trim(instrument.security_id) = trim(history.security_id)
    JOIN portfolios portfolio
      ON trim(portfolio.portfolio_id) = trim(history.portfolio_id)
    WHERE history.portfolio_id LIKE :portfolio_pattern
      AND history.position_date <= :effective_date
      AND upper(trim(instrument.currency)) = :from_currency
      AND upper(trim(portfolio.base_currency)) = :to_currency
),
affected_snapshots AS (
    SELECT snapshot.*
    FROM daily_position_snapshots snapshot
    JOIN instruments instrument
      ON trim(instrument.security_id) = trim(snapshot.security_id)
    JOIN portfolios portfolio
      ON trim(portfolio.portfolio_id) = trim(snapshot.portfolio_id)
    WHERE snapshot.portfolio_id LIKE :portfolio_pattern
      AND snapshot.date BETWEEN :effective_date AND :window_end_date
      AND upper(trim(instrument.currency)) = :from_currency
      AND upper(trim(portfolio.base_currency)) = :to_currency
),
affected_jobs AS (
    SELECT job.*
    FROM portfolio_valuation_jobs job
    JOIN instruments instrument
      ON trim(instrument.security_id) = trim(job.security_id)
    JOIN portfolios portfolio
      ON trim(portfolio.portfolio_id) = trim(job.portfolio_id)
    WHERE job.portfolio_id LIKE :portfolio_pattern
      AND job.valuation_date BETWEEN :effective_date AND :window_end_date
      AND upper(trim(instrument.currency)) = :from_currency
      AND upper(trim(portfolio.base_currency)) = :to_currency
)
SELECT
    (SELECT count(*) FROM affected_histories) AS durable_affected_position_histories,
    (
        SELECT count(*) FROM affected_jobs
        WHERE status = 'FAILED'
          AND failure_reason LIKE 'Missing exact-date FX rate%'
    ) AS failed_valuation_jobs,
    (
        SELECT count(*) FROM affected_snapshots
        WHERE valuation_status = 'FAILED'
          AND market_price IS NULL
          AND market_value IS NULL
          AND market_value_local IS NULL
          AND unrealized_gain_loss IS NULL
          AND unrealized_gain_loss_local IS NULL
          AND unrealized_price_gain_loss IS NULL
          AND unrealized_fx_gain_loss IS NULL
    ) AS failed_snapshots_without_market_values,
    (
        SELECT count(*) FROM position_timeseries series
        JOIN instruments instrument
          ON trim(instrument.security_id) = trim(series.security_id)
        JOIN portfolios portfolio
          ON trim(portfolio.portfolio_id) = trim(series.portfolio_id)
        WHERE series.portfolio_id LIKE :portfolio_pattern
          AND series.date = :effective_date
          AND upper(trim(instrument.currency)) = :from_currency
          AND upper(trim(portfolio.base_currency)) = :to_currency
    ) AS affected_position_timeseries,
    (
        SELECT count(*) FROM portfolio_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date = :effective_date
    ) AS affected_portfolio_timeseries,
    (
        SELECT count(*)
        FROM daily_position_snapshots snapshot
        JOIN instruments instrument
          ON trim(instrument.security_id) = trim(snapshot.security_id)
        JOIN portfolios portfolio
          ON trim(portfolio.portfolio_id) = trim(snapshot.portfolio_id)
        WHERE snapshot.portfolio_id LIKE :portfolio_pattern
          AND snapshot.date = :effective_date
          AND snapshot.valuation_status = 'VALUED_CURRENT'
          AND NOT (
              upper(trim(instrument.currency)) = :from_currency
              AND upper(trim(portfolio.base_currency)) = :to_currency
          )
    ) AS unaffected_current_snapshots,
    (
        SELECT count(*) FROM portfolio_valuation_jobs
        WHERE portfolio_id LIKE :portfolio_pattern
          AND status IN ('PENDING', 'PROCESSING')
    ) AS open_valuation_jobs,
    (
        SELECT count(*) FROM outbox_events
        WHERE status = 'PENDING'
    ) AS pending_outbox_events,
    (
        SELECT count(*) FROM outbox_events
        WHERE status = 'FAILED'
    ) AS failed_outbox_events
"""


_FX_CORRECTED_DERIVED_STATE_SQL = """
WITH affected_snapshots AS (
    SELECT snapshot.*
    FROM daily_position_snapshots snapshot
    JOIN instruments instrument
      ON trim(instrument.security_id) = trim(snapshot.security_id)
    JOIN portfolios portfolio
      ON trim(portfolio.portfolio_id) = trim(snapshot.portfolio_id)
    WHERE snapshot.portfolio_id LIKE :portfolio_pattern
      AND snapshot.date = :effective_date
      AND upper(trim(instrument.currency)) = :from_currency
      AND upper(trim(portfolio.base_currency)) = :to_currency
),
affected_valuation_jobs AS (
    SELECT job.*
    FROM portfolio_valuation_jobs job
    JOIN instruments instrument
      ON trim(instrument.security_id) = trim(job.security_id)
    JOIN portfolios portfolio
      ON trim(portfolio.portfolio_id) = trim(job.portfolio_id)
    WHERE job.portfolio_id LIKE :portfolio_pattern
      AND job.valuation_date = :effective_date
      AND upper(trim(instrument.currency)) = :from_currency
      AND upper(trim(portfolio.base_currency)) = :to_currency
),
affected_position_timeseries AS (
    SELECT series.*
    FROM position_timeseries series
    JOIN instruments instrument
      ON trim(instrument.security_id) = trim(series.security_id)
    JOIN portfolios portfolio
      ON trim(portfolio.portfolio_id) = trim(series.portfolio_id)
    WHERE series.portfolio_id LIKE :portfolio_pattern
      AND series.date BETWEEN :effective_date AND :window_end_date
      AND upper(trim(instrument.currency)) = :from_currency
      AND upper(trim(portfolio.base_currency)) = :to_currency
)
SELECT
    (
        SELECT rate
        FROM fx_rates
        WHERE upper(trim(from_currency)) = :from_currency
          AND upper(trim(to_currency)) = :to_currency
          AND rate_date = :effective_date
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
    ) AS observed_rate,
    (
        SELECT count(*)
        FROM affected_snapshots
        WHERE updated_at >= :correction_started_at
    ) AS corrected_affected_snapshots,
    (
        SELECT coalesce(sum(market_value), 0)
        FROM affected_snapshots
    ) AS corrected_affected_market_value,
    (
        SELECT coalesce(sum(unrealized_price_gain_loss), 0)
        FROM affected_snapshots
    ) AS corrected_unrealized_price,
    (
        SELECT coalesce(sum(unrealized_fx_gain_loss), 0)
        FROM affected_snapshots
    ) AS corrected_unrealized_fx,
    (
        SELECT coalesce(sum(unrealized_gain_loss), 0)
        FROM affected_snapshots
    ) AS corrected_unrealized_total,
    (
        SELECT coalesce(sum(market_value), 0)
        FROM daily_position_snapshots
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date BETWEEN :effective_date AND :window_end_date
    ) AS corrected_total_market_value,
    (
        SELECT count(*)
        FROM affected_valuation_jobs
        WHERE status = 'COMPLETE'
          AND updated_at >= :correction_started_at
    ) AS corrected_valuation_jobs,
    (
        SELECT count(*)
        FROM affected_position_timeseries
        WHERE updated_at >= :correction_started_at
    ) AS corrected_position_timeseries,
    (
        SELECT count(*)
        FROM portfolio_timeseries
        WHERE portfolio_id LIKE :portfolio_pattern
          AND date BETWEEN :effective_date AND :window_end_date
          AND updated_at >= :correction_started_at
    ) AS corrected_portfolio_timeseries,
    (
        SELECT count(*)
        FROM daily_position_snapshots snapshot
        JOIN instruments instrument
          ON trim(instrument.security_id) = trim(snapshot.security_id)
        JOIN portfolios portfolio
          ON trim(portfolio.portfolio_id) = trim(snapshot.portfolio_id)
        WHERE snapshot.portfolio_id LIKE :portfolio_pattern
          AND snapshot.date < :effective_date
          AND snapshot.updated_at >= :correction_started_at
          AND upper(trim(instrument.currency)) = :from_currency
          AND upper(trim(portfolio.base_currency)) = :to_currency
    ) AS unexpected_prior_affected_snapshot_updates,
    (
        SELECT count(*)
        FROM processed_events
        WHERE service_name = 'fx-rate-revaluation-trigger'
          AND processed_at >= :correction_started_at
    ) AS processed_observations,
    (
        SELECT count(*)
        FROM reprocessing_jobs
        WHERE job_type = 'RESET_FX_WATERMARKS'
          AND payload->>'from_currency' = :from_currency
          AND payload->>'to_currency' = :to_currency
          AND payload->>'earliest_impacted_date' = :effective_date_text
          AND status = 'COMPLETE'
          AND updated_at >= :correction_started_at
    ) AS completed_pair_replay_jobs,
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
        FROM reprocessing_jobs
        WHERE job_type = 'RESET_FX_WATERMARKS'
          AND payload->>'from_currency' = :from_currency
          AND payload->>'to_currency' = :to_currency
          AND status IN ('PENDING', 'PROCESSING')
    ) AS open_pair_replay_jobs,
    (
        SELECT count(*)
        FROM reprocessing_jobs
        WHERE job_type = 'RESET_FX_WATERMARKS'
          AND payload->>'from_currency' = :from_currency
          AND payload->>'to_currency' = :to_currency
          AND status = 'FAILED'
    ) AS failed_pair_replay_jobs,
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
"""


def corrected_direct_fx_rate(*, initial_rate: Decimal, multiplier: Decimal) -> Decimal:
    """Apply one governed positive correction at ingestion precision."""

    if initial_rate <= 0:
        raise ValueError("initial_rate must be positive")
    if multiplier <= 0 or multiplier == 1:
        raise ValueError("FX correction multiplier must be positive and not equal to 1")
    return (initial_rate * multiplier).quantize(RATE_QUANTUM)


def build_fx_rate_correction_payload(
    *,
    from_currency: str,
    to_currency: str,
    effective_date: str,
    corrected_rate: Decimal,
) -> list[dict[str, str]]:
    """Build the public ingestion payload for one direct-pair correction."""

    normalized_from = from_currency.strip().upper()
    normalized_to = to_currency.strip().upper()
    if normalized_from == normalized_to:
        raise ValueError("FX correction requires two different currencies")
    date.fromisoformat(effective_date)
    if corrected_rate <= 0:
        raise ValueError("corrected_rate must be positive")
    return [
        {
            "from_currency": normalized_from,
            "to_currency": normalized_to,
            "rate_date": effective_date,
            "rate": f"{corrected_rate:.6f}",
        }
    ]


def build_fx_valuation_expectations(
    *,
    specs: Sequence[SyntheticInstrumentSpec],
    rates_to_base: Mapping[str, Decimal],
    from_currency: str,
    to_currency: str,
    initial_rate: Decimal,
    corrected_rate: Decimal,
    portfolio_count: int,
) -> FxValuationExpectations:
    """Calculate expected value and P&L independently of runtime output."""

    if portfolio_count <= 0:
        raise ValueError("portfolio_count must be positive")
    normalized_from = from_currency.strip().upper()
    normalized_to = to_currency.strip().upper()
    if normalized_from == normalized_to:
        raise ValueError("FX correction requires two different currencies")

    affected_count = 0
    affected_market_value = Decimal(0)
    total_market_value = Decimal(0)
    unrealized_price = Decimal(0)
    unrealized_fx = Decimal(0)
    unrealized_total = Decimal(0)
    for spec in specs:
        currency = spec.currency.strip().upper()
        current_rate = Decimal(1) if currency == normalized_to else rates_to_base[currency]
        if currency == normalized_from:
            affected_count += 1
            current_rate = corrected_rate
            cost_basis_base = spec.trade_price * initial_rate
            market_value_base = spec.market_price * corrected_rate
            price_component = (spec.market_price - spec.trade_price) * corrected_rate
            fx_component = spec.trade_price * corrected_rate - cost_basis_base
            affected_market_value += market_value_base
            unrealized_price += price_component
            unrealized_fx += fx_component
            unrealized_total += market_value_base - cost_basis_base
        total_market_value += spec.market_price * current_rate

    if affected_count == 0:
        raise ValueError(
            f"FX correction pair {normalized_from}/{normalized_to} affects no instruments"
        )

    scale = Decimal(portfolio_count)
    return FxValuationExpectations(
        affected_instrument_count=affected_count,
        daily_affected_market_value=(affected_market_value * scale).quantize(MONEY_QUANTUM),
        daily_total_market_value=(total_market_value * scale).quantize(MONEY_QUANTUM),
        daily_affected_unrealized_price=(unrealized_price * scale).quantize(MONEY_QUANTUM),
        daily_affected_unrealized_fx=(unrealized_fx * scale).quantize(MONEY_QUANTUM),
        daily_affected_unrealized_total=(unrealized_total * scale).quantize(MONEY_QUANTUM),
    )


def wait_for_missing_exact_date_fx_failure(
    *,
    row_reader: RowReader,
    run_id: str,
    from_currency: str,
    to_currency: str,
    valuation_date: str,
    portfolio_count: int,
    affected_instrument_count: int,
    total_instrument_count: int,
    timeout_seconds: int,
    poll_interval_seconds: float = 5,
) -> FxMissingRateFailureEvidence:
    """Wait until missing exact-date FX is proven fail-closed without losing holdings."""

    if portfolio_count <= 0 or affected_instrument_count <= 0:
        raise ValueError("portfolio and affected instrument counts must be positive")
    if total_instrument_count <= affected_instrument_count:
        raise ValueError("the recovery workload must include unaffected control instruments")
    normalized_from_currency = from_currency.strip().upper()
    normalized_to_currency = to_currency.strip().upper()
    effective_date = date.fromisoformat(valuation_date)
    params = {
        "portfolio_pattern": f"LOAD_{run_id}_PF_%",
        "from_currency": normalized_from_currency,
        "to_currency": normalized_to_currency,
        "effective_date": effective_date,
    }
    expected_affected = portfolio_count * affected_instrument_count
    expected_unaffected = portfolio_count * (total_instrument_count - affected_instrument_count)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        row = row_reader(_FX_MISSING_RATE_FAILURE_SQL, params)
        if int(row["failed_outbox_events"]):
            raise RuntimeError("Missing-rate workload produced failed outbox events")
        if (
            int(row["durable_affected_position_histories"]) == expected_affected
            and int(row["failed_valuation_jobs"]) == expected_affected
            and int(row["failed_snapshots_without_market_values"]) == expected_affected
            and int(row["affected_position_timeseries"]) == 0
            and int(row["affected_portfolio_timeseries"]) == 0
            and int(row["unaffected_current_snapshots"]) == expected_unaffected
            and int(row["open_valuation_jobs"]) == 0
            and int(row["pending_outbox_events"]) == 0
        ):
            return FxMissingRateFailureEvidence(
                observed_at=datetime.now().astimezone().isoformat(),
                from_currency=normalized_from_currency,
                to_currency=normalized_to_currency,
                valuation_date=valuation_date,
                expected_affected_positions=expected_affected,
                durable_affected_position_histories=int(row["durable_affected_position_histories"]),
                failed_valuation_jobs=int(row["failed_valuation_jobs"]),
                failed_snapshots_without_market_values=int(
                    row["failed_snapshots_without_market_values"]
                ),
                affected_position_timeseries=int(row["affected_position_timeseries"]),
                affected_portfolio_timeseries=int(row["affected_portfolio_timeseries"]),
                expected_unaffected_snapshots=expected_unaffected,
                unaffected_current_snapshots=int(row["unaffected_current_snapshots"]),
            )
        time.sleep(poll_interval_seconds)
    raise TimeoutError("Missing exact-date FX did not reach the required fail-closed state")


def wait_for_fx_corrected_derived_state(
    *,
    row_reader: RowReader,
    run_id: str,
    from_currency: str,
    to_currency: str,
    effective_date: str,
    window_start_date: str,
    window_end_date: str,
    business_date_count: int,
    affected_business_date_count: int,
    portfolio_count: int,
    expectations: FxValuationExpectations,
    initial_rate: Decimal,
    corrected_rate: Decimal,
    correction_started_at: datetime,
    timeout_seconds: int,
    expected_pair_replay_jobs: int,
    poll_interval_seconds: float = 5,
) -> FxDerivedStateCorrectionEvidence:
    """Wait for exact pair-scoped rematerialization and idempotency evidence."""

    if business_date_count <= 0:
        raise ValueError("business_date_count must be positive")
    if affected_business_date_count <= 0 or affected_business_date_count > business_date_count:
        raise ValueError("affected_business_date_count must be within the business-date window")
    if date.fromisoformat(window_start_date) > date.fromisoformat(window_end_date):
        raise ValueError("window_start_date must not be after window_end_date")
    expected_affected_rows = (
        portfolio_count * expectations.affected_instrument_count * affected_business_date_count
    )
    expected_portfolio_rows = portfolio_count * affected_business_date_count
    affected_window_scale = Decimal(affected_business_date_count)
    expected_values = {
        "affected_market_value": expectations.daily_affected_market_value * affected_window_scale,
        "total_market_value": expectations.daily_total_market_value * affected_window_scale,
        "unrealized_price": expectations.daily_affected_unrealized_price * affected_window_scale,
        "unrealized_fx": expectations.daily_affected_unrealized_fx * affected_window_scale,
        "unrealized_total": expectations.daily_affected_unrealized_total * affected_window_scale,
    }
    normalized_from_currency = from_currency.strip().upper()
    normalized_to_currency = to_currency.strip().upper()
    params = {
        "portfolio_pattern": f"LOAD_{run_id}_PF_%",
        "from_currency": normalized_from_currency,
        "to_currency": normalized_to_currency,
        "effective_date": date.fromisoformat(effective_date),
        "effective_date_text": effective_date,
        "window_start_date": date.fromisoformat(window_start_date),
        "window_end_date": date.fromisoformat(window_end_date),
        "correction_started_at": correction_started_at,
    }
    started = time.perf_counter()
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        row = row_reader(_FX_CORRECTED_DERIVED_STATE_SQL, params)
        failure_counts = {
            name: int(row[name])
            for name in (
                "failed_pair_replay_jobs",
                "failed_valuation_jobs",
                "failed_aggregation_jobs",
                "failed_outbox_events",
            )
        }
        if any(failure_counts.values()):
            raise RuntimeError(f"FX correction entered FAILED state before drain: {failure_counts}")

        observed_values = {
            "affected_market_value": Decimal(str(row["corrected_affected_market_value"])),
            "total_market_value": Decimal(str(row["corrected_total_market_value"])),
            "unrealized_price": Decimal(str(row["corrected_unrealized_price"])),
            "unrealized_fx": Decimal(str(row["corrected_unrealized_fx"])),
            "unrealized_total": Decimal(str(row["corrected_unrealized_total"])),
        }
        if (
            Decimal(str(row["observed_rate"])) == corrected_rate
            and int(row["corrected_affected_snapshots"]) == expected_affected_rows
            and int(row["corrected_valuation_jobs"]) == expected_affected_rows
            and int(row["corrected_position_timeseries"]) == expected_affected_rows
            and int(row["corrected_portfolio_timeseries"]) == expected_portfolio_rows
            and int(row["processed_observations"]) == 1
            and int(row["completed_pair_replay_jobs"]) == expected_pair_replay_jobs
            and int(row["unexpected_prior_affected_snapshot_updates"]) == 0
            and int(row["open_valuation_jobs"]) == 0
            and int(row["open_aggregation_jobs"]) == 0
            and int(row["open_pair_replay_jobs"]) == 0
            and int(row["pending_outbox_events"]) == 0
            and observed_values == expected_values
        ):
            return FxDerivedStateCorrectionEvidence(
                correction_started_at=correction_started_at.isoformat(),
                from_currency=normalized_from_currency,
                to_currency=normalized_to_currency,
                effective_date=effective_date,
                window_start_date=window_start_date,
                window_end_date=window_end_date,
                business_date_count=business_date_count,
                drain_seconds=round(time.perf_counter() - started, 3),
                initial_rate=f"{initial_rate:.6f}",
                corrected_rate=f"{corrected_rate:.6f}",
                expected_affected_snapshots=expected_affected_rows,
                corrected_affected_snapshots=int(row["corrected_affected_snapshots"]),
                expected_valuation_jobs=expected_affected_rows,
                corrected_valuation_jobs=int(row["corrected_valuation_jobs"]),
                expected_position_timeseries=expected_affected_rows,
                corrected_position_timeseries=int(row["corrected_position_timeseries"]),
                expected_portfolio_timeseries=expected_portfolio_rows,
                corrected_portfolio_timeseries=int(row["corrected_portfolio_timeseries"]),
                processed_observations=int(row["processed_observations"]),
                completed_pair_replay_jobs=int(row["completed_pair_replay_jobs"]),
                expected_affected_market_value=f"{expected_values['affected_market_value']:.10f}",
                corrected_affected_market_value=f"{observed_values['affected_market_value']:.10f}",
                expected_total_market_value=f"{expected_values['total_market_value']:.10f}",
                corrected_total_market_value=f"{observed_values['total_market_value']:.10f}",
                expected_unrealized_price=f"{expected_values['unrealized_price']:.10f}",
                corrected_unrealized_price=f"{observed_values['unrealized_price']:.10f}",
                expected_unrealized_fx=f"{expected_values['unrealized_fx']:.10f}",
                corrected_unrealized_fx=f"{observed_values['unrealized_fx']:.10f}",
                expected_unrealized_total=f"{expected_values['unrealized_total']:.10f}",
                corrected_unrealized_total=f"{observed_values['unrealized_total']:.10f}",
                unexpected_prior_affected_snapshot_updates=int(
                    row["unexpected_prior_affected_snapshot_updates"]
                ),
            )
        time.sleep(poll_interval_seconds)
    raise TimeoutError("FX correction did not fully rematerialize before timeout.")
