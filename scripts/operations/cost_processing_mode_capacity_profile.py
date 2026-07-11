"""Profile ordered append and backdated rebuild cost-basis workloads."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[2]
for source_root in (
    REPO_ROOT,
    REPO_ROOT / "src" / "libs" / "portfolio-common",
    REPO_ROOT / "src" / "services" / "calculators" / "cost_calculator_service",
):
    sys.path.insert(0, str(source_root))

from scripts.operations.cost_history_capacity_profile import (  # noqa: E402
    SUPPORTED_METHODS,
    build_capacity_timeline,
)
from src.services.calculators.cost_calculator_service.app.transaction_processor import (  # noqa: E402
    build_transaction_processor,
)

SCHEMA_VERSION = "lotus-core.cost-processing-mode-capacity-profile.v3"


@dataclass(frozen=True, slots=True)
class ProcessingModeMeasurement:
    workload_mode: str
    cost_basis_method: str
    history_transaction_count: int
    request_count: int
    recalculated_row_count: int
    restored_open_lot_count: int
    duration_seconds: float
    average_request_latency_ms: float
    requests_per_second: float
    recalculated_rows_per_second: float
    error_count: int
    ending_open_quantity: str


def _open_lot_checkpoint(
    timeline: list[dict[str, str]],
    *,
    cost_basis_method: str,
) -> tuple[list[dict[str, object]], int]:
    processed, errors, states = build_transaction_processor(cost_basis_method).process_transactions(
        [], timeline
    )
    if errors or len(processed) != len(timeline):
        raise RuntimeError("Capacity profile prefix failed financial validation")

    source_by_id = {row["transaction_id"]: row for row in timeline}
    checkpoint: list[dict[str, object]] = []
    for source_transaction_id, state in states.items():
        if state.quantity <= Decimal(0):
            continue
        source = dict(source_by_id[source_transaction_id])
        source["quantity"] = state.quantity
        source["net_cost_local"] = state.cost_local
        source["net_cost"] = state.cost_base
        checkpoint.append(source)
    return checkpoint, len(errors)


def _appended_sell(timeline: list[dict[str, str]]) -> dict[str, str]:
    latest_date = max(datetime.fromisoformat(row["transaction_date"]) for row in timeline)
    return {
        **timeline[-1],
        "transaction_id": "SELL-ORDERED-APPEND",
        "transaction_date": (latest_date + timedelta(seconds=1)).isoformat(),
        "transaction_type": "SELL",
        "quantity": "1",
        "price": "13",
        "gross_transaction_amount": "13",
    }


def _disposal_checkpoint(
    checkpoint: list[dict[str, object]],
    *,
    cost_basis_method: str,
    required_quantity: Decimal,
) -> list[dict[str, object]]:
    if cost_basis_method == "AVCO":
        if not checkpoint:
            return []
        aggregate = dict(checkpoint[-1])
        aggregate["quantity"] = sum(
            (Decimal(str(lot["quantity"])) for lot in checkpoint), Decimal(0)
        )
        aggregate["net_cost_local"] = sum(
            (Decimal(str(lot["net_cost_local"])) for lot in checkpoint), Decimal(0)
        )
        aggregate["net_cost"] = sum(
            (Decimal(str(lot["net_cost"])) for lot in checkpoint), Decimal(0)
        )
        return [aggregate]

    selected_lots: list[dict[str, object]] = []
    covered_quantity = Decimal(0)
    for lot in checkpoint:
        selected_lots.append(lot)
        covered_quantity += Decimal(str(lot["quantity"]))
        if covered_quantity >= required_quantity:
            break
    return selected_lots


def _appended_buy(timeline: list[dict[str, str]]) -> dict[str, str]:
    latest_date = max(datetime.fromisoformat(row["transaction_date"]) for row in timeline)
    return {
        **timeline[-1],
        "transaction_id": "BUY-ORDERED-APPEND",
        "transaction_date": (latest_date + timedelta(seconds=1)).isoformat(),
        "transaction_type": "BUY",
        "quantity": "1",
        "price": "11",
        "gross_transaction_amount": "11",
    }


def _backdated_buy(timeline: list[dict[str, str]]) -> dict[str, str]:
    first_date = datetime.fromisoformat(timeline[0]["transaction_date"])
    return {
        **timeline[0],
        "transaction_id": "BUY-BACKDATED-INSERT",
        "transaction_date": (first_date + timedelta(microseconds=1)).isoformat(),
        "transaction_type": "BUY",
        "quantity": "1",
        "price": "9",
        "gross_transaction_amount": "9",
    }


def run_processing_mode_profile(
    *,
    history_counts: Sequence[int],
    cost_basis_methods: Sequence[str],
    append_iterations: int,
    clock: Callable[[], float] = perf_counter,
) -> dict[str, object]:
    counts = sorted(set(history_counts))
    if not counts or any(count <= 0 for count in counts):
        raise ValueError("history_counts must contain positive values")
    if append_iterations <= 0:
        raise ValueError("append_iterations must be positive")
    methods = tuple(method.strip().upper() for method in cost_basis_methods)
    unsupported_methods = sorted(set(methods) - set(SUPPORTED_METHODS))
    if not methods or unsupported_methods:
        raise ValueError(
            f"cost_basis_methods must contain FIFO or AVCO; unsupported={unsupported_methods}"
        )

    measurements: list[ProcessingModeMeasurement] = []
    for method in methods:
        for history_count in counts:
            timeline = build_capacity_timeline(history_count)
            checkpoint, prefix_error_count = _open_lot_checkpoint(
                timeline,
                cost_basis_method=method,
            )
            opening_event = _appended_buy(timeline)
            append_event = _appended_sell(timeline)
            disposal_checkpoint = _disposal_checkpoint(
                checkpoint,
                cost_basis_method=method,
                required_quantity=Decimal(append_event["quantity"]),
            )

            opening_started = clock()
            opening_error_count = prefix_error_count
            opening_states = {}
            for _ in range(append_iterations):
                processed, errors, opening_states = build_transaction_processor(
                    method
                ).process_increment(
                    initial_open_lots_raw=[],
                    new_transactions_raw=[opening_event],
                )
                opening_error_count += len(errors)
                if len(processed) != 1:
                    raise RuntimeError("Ordered opening profile did not process exactly one event")
            opening_duration = max(clock() - opening_started, 0.0)
            measurements.append(
                _measurement(
                    workload_mode="ordered_opening_append",
                    cost_basis_method=method,
                    history_transaction_count=history_count,
                    request_count=append_iterations,
                    recalculated_row_count=append_iterations,
                    restored_open_lot_count=0,
                    duration_seconds=opening_duration,
                    error_count=opening_error_count,
                    ending_open_quantity=_total_open_quantity(opening_states),
                )
            )

            append_started = clock()
            append_error_count = prefix_error_count
            append_states = {}
            for _ in range(append_iterations):
                processed, errors, append_states = build_transaction_processor(
                    method
                ).process_increment(
                    initial_open_lots_raw=disposal_checkpoint,
                    new_transactions_raw=[append_event],
                )
                append_error_count += len(errors)
                if len(processed) != 1:
                    raise RuntimeError("Ordered append profile did not process exactly one event")
            append_duration = max(clock() - append_started, 0.0)
            measurements.append(
                _measurement(
                    workload_mode="ordered_disposal_append",
                    cost_basis_method=method,
                    history_transaction_count=history_count,
                    request_count=append_iterations,
                    recalculated_row_count=append_iterations,
                    restored_open_lot_count=len(disposal_checkpoint),
                    duration_seconds=append_duration,
                    error_count=append_error_count,
                    ending_open_quantity=_total_open_quantity(append_states),
                )
            )

            backdated_started = clock()
            processed, errors, backdated_states = build_transaction_processor(
                method
            ).process_transactions([], [*timeline, _backdated_buy(timeline)])
            backdated_duration = max(clock() - backdated_started, 0.0)
            if len(processed) != history_count + 1:
                raise RuntimeError("Backdated profile did not rebuild the complete history")
            measurements.append(
                _measurement(
                    workload_mode="backdated_rebuild",
                    cost_basis_method=method,
                    history_transaction_count=history_count,
                    request_count=1,
                    recalculated_row_count=history_count + 1,
                    restored_open_lot_count=0,
                    duration_seconds=backdated_duration,
                    error_count=len(errors),
                    ending_open_quantity=_total_open_quantity(backdated_states),
                )
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": {
            "layer": "cost_basis_calculation",
            "includes_database_io": False,
            "includes_kafka_io": False,
            "ordered_opening_append_requires_prior_lot_restore": False,
            "ordered_fifo_disposal_restores_only_quantity_covering_lots": True,
            "ordered_avco_disposal_restores_one_aggregate_pool_source": True,
            "backdated_rebuild_recalculates_complete_timeline": True,
        },
        "measurements": [asdict(measurement) for measurement in measurements],
    }


def _measurement(
    *,
    workload_mode: str,
    cost_basis_method: str,
    history_transaction_count: int,
    request_count: int,
    recalculated_row_count: int,
    restored_open_lot_count: int,
    duration_seconds: float,
    error_count: int,
    ending_open_quantity: Decimal,
) -> ProcessingModeMeasurement:
    request_rate = request_count / duration_seconds if duration_seconds > 0 else 0.0
    row_rate = recalculated_row_count / duration_seconds if duration_seconds > 0 else 0.0
    latency_ms = duration_seconds * 1000 / request_count
    return ProcessingModeMeasurement(
        workload_mode=workload_mode,
        cost_basis_method=cost_basis_method,
        history_transaction_count=history_transaction_count,
        request_count=request_count,
        recalculated_row_count=recalculated_row_count,
        restored_open_lot_count=restored_open_lot_count,
        duration_seconds=round(duration_seconds, 6),
        average_request_latency_ms=round(latency_ms, 3),
        requests_per_second=round(request_rate, 3),
        recalculated_rows_per_second=round(row_rate, 3),
        error_count=error_count,
        ending_open_quantity=str(ending_open_quantity),
    )


def _total_open_quantity(states: dict[str, object]) -> Decimal:
    return sum((getattr(state, "quantity") for state in states.values()), Decimal(0))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-counts", nargs="+", type=int, default=[1000, 4000, 8000])
    parser.add_argument(
        "--cost-basis-methods",
        nargs="+",
        default=list(SUPPORTED_METHODS),
    )
    parser.add_argument("--append-iterations", type=int, default=5)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_processing_mode_profile(
        history_counts=args.history_counts,
        cost_basis_methods=args.cost_basis_methods,
        append_iterations=args.append_iterations,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
