"""Tests for effective-dated market-price correction workload evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from scripts.operations.performance.market_price_correction import (
    SyntheticInstrumentSpec,
    apply_market_price_correction,
    build_synthetic_business_date_window,
    wait_for_corrected_derived_state,
)


def _instrument(*, security_id: str, market_price: str) -> SyntheticInstrumentSpec:
    return SyntheticInstrumentSpec(
        security_id=security_id,
        currency="USD",
        trade_price=Decimal("50.00"),
        market_price=Decimal(market_price),
    )


def test_apply_market_price_correction_uses_ingestion_precision_without_mutation() -> None:
    specs = [
        _instrument(security_id="SEC-1", market_price="50.50"),
        _instrument(security_id="SEC-2", market_price="51.76"),
    ]

    corrected = apply_market_price_correction(specs=specs, multiplier=Decimal("1.05"))

    assert [spec.market_price for spec in corrected] == [Decimal("53.02"), Decimal("54.35")]
    assert [spec.market_price for spec in specs] == [Decimal("50.50"), Decimal("51.76")]


@pytest.mark.parametrize("multiplier", [Decimal("0"), Decimal("-1"), Decimal("1")])
def test_apply_market_price_correction_rejects_non_corrections(multiplier: Decimal) -> None:
    with pytest.raises(ValueError, match="positive and not equal to 1"):
        apply_market_price_correction(
            specs=[_instrument(security_id="SEC-1", market_price="50.50")],
            multiplier=multiplier,
        )


def test_synthetic_business_date_window_skips_weekends() -> None:
    assert build_synthetic_business_date_window(
        as_of_date="2026-07-13",
        business_date_count=3,
    ) == ("2026-07-09", "2026-07-10", "2026-07-13")


@pytest.mark.parametrize("business_date_count", [0, -1])
def test_synthetic_business_date_window_rejects_non_positive_counts(
    business_date_count: int,
) -> None:
    with pytest.raises(ValueError, match="business_date_count must be positive"):
        build_synthetic_business_date_window(
            as_of_date="2026-07-13",
            business_date_count=business_date_count,
        )


def test_synthetic_business_date_window_rejects_weekend_as_of_date() -> None:
    with pytest.raises(ValueError, match="as_of_date must be a weekday"):
        build_synthetic_business_date_window(
            as_of_date="2026-07-12",
            business_date_count=1,
        )


def test_wait_requires_every_post_correction_derived_stage() -> None:
    captured: dict[str, object] = {}
    correction_started_at = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)

    def row_reader(query: str, params: Mapping[str, Any]) -> dict[str, object]:
        captured["query"] = query
        captured["params"] = params
        return {
            "corrected_snapshots": 12,
            "corrected_market_value": Decimal("660.0000000000"),
            "corrected_valuation_jobs": 12,
            "corrected_position_timeseries": 12,
            "corrected_portfolio_timeseries": 4,
            "open_valuation_jobs": 0,
            "open_aggregation_jobs": 0,
            "failed_valuation_jobs": 0,
            "failed_aggregation_jobs": 0,
            "pending_outbox_events": 0,
            "failed_outbox_events": 0,
        }

    evidence = wait_for_corrected_derived_state(
        row_reader=row_reader,
        run_id="RUN1",
        window_start_date="2026-07-14",
        window_end_date="2026-07-15",
        business_date_count=2,
        portfolio_count=2,
        transaction_count=6,
        expected_daily_market_value=Decimal("330.0000000000"),
        correction_started_at=correction_started_at,
        timeout_seconds=1,
    )

    assert evidence.drain_seconds >= 0
    assert evidence.business_date_count == 2
    assert evidence.window_start_date == "2026-07-14"
    assert evidence.window_end_date == "2026-07-15"
    assert evidence.expected_snapshots == evidence.corrected_snapshots == 12
    assert evidence.expected_valuation_jobs == evidence.corrected_valuation_jobs == 12
    assert evidence.expected_position_timeseries == evidence.corrected_position_timeseries == 12
    assert evidence.expected_portfolio_timeseries == evidence.corrected_portfolio_timeseries == 4
    assert (
        evidence.expected_window_market_value
        == evidence.corrected_window_market_value
        == "660.0000000000"
    )
    query = str(captured["query"])
    assert query.count("updated_at >= :correction_started_at") == 4
    assert query.count("BETWEEN :window_start_date AND :window_end_date") == 4
    assert "status IN ('PENDING', 'PROCESSING')" in query
    assert captured["params"] == {
        "portfolio_pattern": "LOAD_RUN1_PF_%",
        "window_start_date": "2026-07-14",
        "window_end_date": "2026-07-15",
        "correction_started_at": correction_started_at,
    }
