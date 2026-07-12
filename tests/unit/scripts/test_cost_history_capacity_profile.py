from __future__ import annotations

import json

import pytest

from scripts.operations.cost_history_capacity_profile import (
    SCHEMA_VERSION,
    build_capacity_timeline,
    run_capacity_profile,
)


def test_capacity_timeline_is_deterministic_and_accumulates_open_lots() -> None:
    timeline = build_capacity_timeline(8)

    assert [row["transaction_type"] for row in timeline] == [
        "BUY",
        "BUY",
        "BUY",
        "SELL",
        "BUY",
        "BUY",
        "BUY",
        "SELL",
    ]
    assert timeline[0]["transaction_id"] == "BUY-00000000"
    assert timeline[-1]["transaction_id"] == "SELL-00000007"
    assert timeline[0]["transaction_date"] < timeline[-1]["transaction_date"]


def test_capacity_timeline_rejects_non_positive_count() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        build_capacity_timeline(0)


def test_capacity_profile_returns_machine_readable_financially_valid_measurements() -> None:
    clock_values = iter((10.0, 10.5, 20.0, 21.0))

    report = run_capacity_profile(
        transaction_counts=[8],
        cost_basis_methods=["fifo", "AVCO"],
        clock=lambda: next(clock_values),
    )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["workload"] == {
        "pattern": "three_buys_then_one_sell",
        "currency": "USD",
        "quantity_per_transaction": "1",
        "buy_price": "10",
        "sell_price": "12",
        "includes_fixture_generation_in_duration": False,
    }
    measurements = report["measurements"]
    assert measurements == [
        {
            "cost_basis_method": "FIFO",
            "transaction_count": 8,
            "duration_seconds": 0.5,
            "transactions_per_second": 16.0,
            "processed_count": 8,
            "error_count": 0,
            "open_lot_state_count": 6,
        },
        {
            "cost_basis_method": "AVCO",
            "transaction_count": 8,
            "duration_seconds": 1.0,
            "transactions_per_second": 8.0,
            "processed_count": 8,
            "error_count": 0,
            "open_lot_state_count": 6,
        },
    ]
    json.dumps(report, allow_nan=False)


def test_capacity_profile_keeps_zero_duration_measurement_json_safe() -> None:
    report = run_capacity_profile(
        transaction_counts=[1],
        cost_basis_methods=["FIFO"],
        clock=lambda: 5.0,
    )

    assert report["measurements"][0]["transactions_per_second"] == 0.0
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    ("counts", "methods", "message"),
    [
        ([], ["FIFO"], "positive values"),
        ([1], ["LIFO"], "unsupported"),
        ([1], [], "unsupported"),
    ],
)
def test_capacity_profile_rejects_invalid_scope(
    counts: list[int], methods: list[str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_capacity_profile(transaction_counts=counts, cost_basis_methods=methods)
