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


def test_wait_requires_every_post_correction_derived_stage() -> None:
    captured: dict[str, object] = {}
    correction_started_at = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)

    def row_reader(query: str, params: Mapping[str, Any]) -> dict[str, object]:
        captured["query"] = query
        captured["params"] = params
        return {
            "corrected_snapshots": 6,
            "corrected_market_value": Decimal("660.0000000000"),
            "corrected_valuation_jobs": 6,
            "corrected_position_timeseries": 6,
            "corrected_portfolio_timeseries": 2,
            "open_valuation_jobs": 0,
            "open_aggregation_jobs": 0,
            "failed_valuation_jobs": 0,
            "failed_aggregation_jobs": 0,
        }

    elapsed = wait_for_corrected_derived_state(
        row_reader=row_reader,
        run_id="RUN1",
        trade_date="2026-07-15",
        portfolio_count=2,
        transaction_count=6,
        expected_market_value=Decimal("660.0000000000"),
        correction_started_at=correction_started_at,
        timeout_seconds=1,
    )

    assert elapsed >= 0
    query = str(captured["query"])
    assert query.count("updated_at >= :correction_started_at") == 4
    assert "status IN ('PENDING', 'PROCESSING')" in query
    assert captured["params"] == {
        "portfolio_pattern": "LOAD_RUN1_PF_%",
        "trade_date": "2026-07-15",
        "correction_started_at": correction_started_at,
    }
