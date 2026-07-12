from __future__ import annotations

import json

import pytest

from scripts.operations.cost_processing_mode_capacity_profile import (
    SCHEMA_VERSION,
    run_processing_mode_profile,
)


def test_processing_mode_profile_separates_append_and_backdated_work() -> None:
    clock_values = iter((5.0, 5.25, 10.0, 10.5, 20.0, 21.0))

    report = run_processing_mode_profile(
        history_counts=[8],
        cost_basis_methods=["FIFO"],
        append_iterations=2,
        clock=lambda: next(clock_values),
    )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["scope"] == {
        "layer": "cost_engine",
        "includes_database_io": False,
        "includes_kafka_io": False,
        "ordered_opening_append_requires_prior_lot_restore": False,
        "ordered_fifo_disposal_restores_only_quantity_covering_lots": True,
        "ordered_avco_disposal_restores_one_aggregate_pool_source": True,
        "backdated_rebuild_recalculates_complete_timeline": True,
    }
    opening, disposal, backdated = report["measurements"]
    assert opening["workload_mode"] == "ordered_opening_append"
    assert opening["request_count"] == 2
    assert opening["average_request_latency_ms"] == 125.0
    assert opening["requests_per_second"] == 8.0
    assert disposal["workload_mode"] == "ordered_disposal_append"
    assert disposal["request_count"] == 2
    assert disposal["recalculated_row_count"] == 2
    assert disposal["restored_open_lot_count"] == 1
    assert disposal["average_request_latency_ms"] == 250.0
    assert disposal["requests_per_second"] == 4.0
    assert disposal["error_count"] == 0
    assert backdated["workload_mode"] == "backdated_rebuild"
    assert backdated["request_count"] == 1
    assert backdated["recalculated_row_count"] == 9
    assert backdated["recalculated_rows_per_second"] == 9.0
    assert backdated["restored_open_lot_count"] == 0
    assert backdated["error_count"] == 0
    json.dumps(report, allow_nan=False)


def test_processing_mode_profile_restores_one_average_cost_pool_source() -> None:
    clock_values = iter((5.0, 5.25, 10.0, 10.5, 20.0, 21.0))

    report = run_processing_mode_profile(
        history_counts=[8],
        cost_basis_methods=["AVCO"],
        append_iterations=2,
        clock=lambda: next(clock_values),
    )

    opening, disposal, backdated = report["measurements"]
    assert disposal["restored_open_lot_count"] == 1
    assert disposal["error_count"] == 0
    assert disposal["ending_open_quantity"] == "3.0000000000"
    assert opening["ending_open_quantity"] == "1"
    assert backdated["ending_open_quantity"] == "5.0000000000"


@pytest.mark.parametrize(
    ("counts", "methods", "iterations", "message"),
    [
        ([], ["FIFO"], 1, "positive values"),
        ([1], ["LIFO"], 1, "unsupported"),
        ([1], [], 1, "unsupported"),
        ([1], ["FIFO"], 0, "append_iterations"),
    ],
)
def test_processing_mode_profile_rejects_invalid_scope(
    counts: list[int], methods: list[str], iterations: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_processing_mode_profile(
            history_counts=counts,
            cost_basis_methods=methods,
            append_iterations=iterations,
        )
