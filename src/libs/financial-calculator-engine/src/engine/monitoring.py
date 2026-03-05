# src/libs/financial-calculator-engine/src/monitoring.py
from prometheus_client import Histogram

RECALCULATION_DEPTH = Histogram(
    "recalculation_depth",
    "Number of historical transactions replayed during a single cost basis recalculation.",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
)

RECALCULATION_DURATION_SECONDS = Histogram(
    "recalculation_duration_seconds",
    "Wall-clock time spent inside the core financial engine's recalculation process.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
