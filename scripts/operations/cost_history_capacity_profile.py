"""Profile cost-basis scaling over deterministic long transaction histories."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[2]
for source_root in (
    REPO_ROOT,
    REPO_ROOT / "src" / "libs" / "portfolio-common",
    REPO_ROOT / "src" / "services" / "calculators" / "cost_calculator_service",
):
    sys.path.insert(0, str(source_root))

from src.services.calculators.cost_calculator_service.app.transaction_processor import (  # noqa: E402
    build_transaction_processor,
)

SCHEMA_VERSION = "lotus-core.cost-history-capacity-profile.v1"
SUPPORTED_METHODS = ("FIFO", "AVCO")


@dataclass(frozen=True, slots=True)
class CapacityMeasurement:
    cost_basis_method: str
    transaction_count: int
    duration_seconds: float
    transactions_per_second: float
    processed_count: int
    error_count: int
    open_lot_state_count: int


def build_capacity_timeline(transaction_count: int) -> list[dict[str, str]]:
    """Build a deterministic three-buy/one-sell accumulating-lot workload."""
    if transaction_count <= 0:
        raise ValueError("transaction_count must be positive")

    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    timeline: list[dict[str, str]] = []
    for index in range(transaction_count):
        is_sell = index % 4 == 3
        transaction_type = "SELL" if is_sell else "BUY"
        price = "12" if is_sell else "10"
        timeline.append(
            {
                "transaction_id": f"{transaction_type}-{index:08d}",
                "portfolio_id": "P-COST-CAPACITY",
                "instrument_id": "I-COST-CAPACITY",
                "security_id": "S-COST-CAPACITY",
                "transaction_date": (started_at + timedelta(seconds=index)).isoformat(),
                "transaction_type": transaction_type,
                "quantity": "1",
                "price": price,
                "gross_transaction_amount": price,
                "trade_currency": "USD",
                "portfolio_base_currency": "USD",
                "transaction_fx_rate": "1",
                "trade_fee": "0",
            }
        )
    return timeline


def run_capacity_profile(
    *,
    transaction_counts: Sequence[int],
    cost_basis_methods: Sequence[str],
    clock: Callable[[], float] = perf_counter,
) -> dict[str, object]:
    """Run the in-memory parser, sorter, and cost engine for each requested workload."""
    counts = sorted(set(transaction_counts))
    if not counts or any(count <= 0 for count in counts):
        raise ValueError("transaction_counts must contain positive values")

    methods = tuple(method.strip().upper() for method in cost_basis_methods)
    unsupported_methods = sorted(set(methods) - set(SUPPORTED_METHODS))
    if not methods or unsupported_methods:
        raise ValueError(
            f"cost_basis_methods must contain FIFO or AVCO; unsupported={unsupported_methods}"
        )

    measurements: list[CapacityMeasurement] = []
    for method in methods:
        for transaction_count in counts:
            timeline = build_capacity_timeline(transaction_count)
            processor = build_transaction_processor(method)
            started = clock()
            processed, errors, open_lot_states = processor.process_transactions([], timeline)
            duration_seconds = max(clock() - started, 0.0)
            throughput = transaction_count / duration_seconds if duration_seconds > 0 else 0.0
            measurements.append(
                CapacityMeasurement(
                    cost_basis_method=method,
                    transaction_count=transaction_count,
                    duration_seconds=round(duration_seconds, 6),
                    transactions_per_second=round(throughput, 3),
                    processed_count=len(processed),
                    error_count=len(errors),
                    open_lot_state_count=len(open_lot_states),
                )
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "workload": {
            "pattern": "three_buys_then_one_sell",
            "currency": "USD",
            "quantity_per_transaction": "1",
            "buy_price": "10",
            "sell_price": "12",
            "includes_fixture_generation_in_duration": False,
        },
        "measurements": [asdict(measurement) for measurement in measurements],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transaction-counts",
        nargs="+",
        type=int,
        default=[1000, 2000, 4000, 8000],
    )
    parser.add_argument(
        "--cost-basis-methods",
        nargs="+",
        default=list(SUPPORTED_METHODS),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_capacity_profile(
        transaction_counts=args.transaction_counts,
        cost_basis_methods=args.cost_basis_methods,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
