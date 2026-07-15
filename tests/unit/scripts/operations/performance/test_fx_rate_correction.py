"""Tests for deterministic direct-pair FX correction evidence."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from scripts.operations.performance.fx_rate_correction import (
    build_fx_rate_correction_payload,
    build_fx_valuation_expectations,
    corrected_direct_fx_rate,
    wait_for_fx_corrected_derived_state,
)
from scripts.operations.performance.market_price_correction import SyntheticInstrumentSpec


def _spec(
    security_id: str,
    currency: str,
    trade_price: str,
    market_price: str,
) -> SyntheticInstrumentSpec:
    return SyntheticInstrumentSpec(
        security_id=security_id,
        currency=currency,
        trade_price=Decimal(trade_price),
        market_price=Decimal(market_price),
    )


def test_fx_expectations_decompose_price_fx_and_total_pnl() -> None:
    initial_rate = Decimal("1.100000")
    corrected_rate = corrected_direct_fx_rate(
        initial_rate=initial_rate,
        multiplier=Decimal("1.05"),
    )

    expectations = build_fx_valuation_expectations(
        specs=[
            _spec("USD-1", "USD", "100", "101"),
            _spec("EUR-1", "EUR", "100", "101"),
        ],
        rates_to_base={"EUR": initial_rate},
        from_currency="EUR",
        to_currency="USD",
        initial_rate=initial_rate,
        corrected_rate=corrected_rate,
        portfolio_count=2,
    )

    assert corrected_rate == Decimal("1.155000")
    assert expectations.affected_instrument_count == 1
    assert expectations.daily_affected_market_value == Decimal("233.3100000000")
    assert expectations.daily_total_market_value == Decimal("435.3100000000")
    assert expectations.daily_affected_unrealized_price == Decimal("2.3100000000")
    assert expectations.daily_affected_unrealized_fx == Decimal("11.0000000000")
    assert expectations.daily_affected_unrealized_total == Decimal("13.3100000000")
    assert (
        expectations.daily_affected_unrealized_price + expectations.daily_affected_unrealized_fx
        == expectations.daily_affected_unrealized_total
    )


def test_fx_correction_payload_normalizes_pair_and_precision() -> None:
    payload = build_fx_rate_correction_payload(
        from_currency=" eur ",
        to_currency="usd",
        effective_date="2026-04-06",
        corrected_rate=Decimal("1.155"),
    )

    assert payload == [
        {
            "from_currency": "EUR",
            "to_currency": "USD",
            "rate_date": "2026-04-06",
            "rate": "1.155000",
        }
    ]


def test_fx_expectations_reject_pair_without_affected_instruments() -> None:
    with pytest.raises(ValueError, match="EUR/USD affects no instruments"):
        build_fx_valuation_expectations(
            specs=[_spec("USD-1", "USD", "100", "101")],
            rates_to_base={"EUR": Decimal("1.100000")},
            from_currency="EUR",
            to_currency="USD",
            initial_rate=Decimal("1.100000"),
            corrected_rate=Decimal("1.155000"),
            portfolio_count=1,
        )


def test_wait_for_fx_correction_requires_exact_runtime_evidence() -> None:
    expectations = build_fx_valuation_expectations(
        specs=[_spec("EUR-1", "EUR", "100", "101")],
        rates_to_base={"EUR": Decimal("1.100000")},
        from_currency="EUR",
        to_currency="USD",
        initial_rate=Decimal("1.100000"),
        corrected_rate=Decimal("1.155000"),
        portfolio_count=2,
    )
    observed_params: list[dict[str, object]] = []

    def row_reader(_sql, params):
        observed_params.append(dict(params))
        return {
            "observed_rate": Decimal("1.155000"),
            "corrected_affected_snapshots": 6,
            "corrected_affected_market_value": Decimal("699.9300000000"),
            "corrected_unrealized_price": Decimal("6.9300000000"),
            "corrected_unrealized_fx": Decimal("33.0000000000"),
            "corrected_unrealized_total": Decimal("39.9300000000"),
            "corrected_total_market_value": Decimal("699.9300000000"),
            "corrected_valuation_jobs": 6,
            "corrected_position_timeseries": 6,
            "corrected_portfolio_timeseries": 6,
            "processed_observations": 1,
            "completed_pair_replay_jobs": 1,
            "open_valuation_jobs": 0,
            "open_aggregation_jobs": 0,
            "open_pair_replay_jobs": 0,
            "failed_pair_replay_jobs": 0,
            "failed_valuation_jobs": 0,
            "failed_aggregation_jobs": 0,
            "pending_outbox_events": 0,
            "failed_outbox_events": 0,
        }

    evidence = wait_for_fx_corrected_derived_state(
        row_reader=row_reader,
        run_id="20260715T000000Z",
        from_currency="EUR",
        to_currency="USD",
        effective_date="2026-04-06",
        window_start_date="2026-04-06",
        window_end_date="2026-04-08",
        business_date_count=3,
        portfolio_count=2,
        expectations=expectations,
        initial_rate=Decimal("1.100000"),
        corrected_rate=Decimal("1.155000"),
        correction_started_at=datetime(2026, 4, 8, 10, tzinfo=timezone.utc),
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert evidence.expected_affected_snapshots == 6
    assert evidence.corrected_affected_snapshots == 6
    assert evidence.processed_observations == 1
    assert evidence.completed_pair_replay_jobs == 1
    assert evidence.expected_unrealized_total == "39.9300000000"
    assert observed_params[0]["from_currency"] == "EUR"
    assert observed_params[0]["to_currency"] == "USD"


def test_wait_for_fx_correction_fails_fast_on_durable_failure() -> None:
    expectations = build_fx_valuation_expectations(
        specs=[_spec("EUR-1", "EUR", "100", "101")],
        rates_to_base={"EUR": Decimal("1.100000")},
        from_currency="EUR",
        to_currency="USD",
        initial_rate=Decimal("1.100000"),
        corrected_rate=Decimal("1.155000"),
        portfolio_count=1,
    )

    with pytest.raises(RuntimeError, match="failed_pair_replay_jobs"):
        wait_for_fx_corrected_derived_state(
            row_reader=lambda _sql, _params: {
                "failed_pair_replay_jobs": 1,
                "failed_valuation_jobs": 0,
                "failed_aggregation_jobs": 0,
                "failed_outbox_events": 0,
            },
            run_id="20260715T000000Z",
            from_currency="EUR",
            to_currency="USD",
            effective_date="2026-04-06",
            window_start_date="2026-04-06",
            window_end_date="2026-04-06",
            business_date_count=1,
            portfolio_count=1,
            expectations=expectations,
            initial_rate=Decimal("1.100000"),
            corrected_rate=Decimal("1.155000"),
            correction_started_at=datetime(2026, 4, 6, 10, tzinfo=timezone.utc),
            timeout_seconds=1,
            poll_interval_seconds=0,
        )
