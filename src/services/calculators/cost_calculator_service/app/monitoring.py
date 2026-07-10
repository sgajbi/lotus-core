from prometheus_client import Counter, Histogram

COST_PROCESSING_EXECUTION_TOTAL = Counter(
    "cost_processing_execution_total",
    "Cost-basis calculations by bounded execution mode and method.",
    labelnames=("mode", "cost_basis_method"),
)

COST_PROCESSING_OPEN_LOTS_RESTORED = Histogram(
    "cost_processing_open_lots_restored",
    "Open source lots restored for an ordered state-dependent cost calculation.",
    labelnames=("cost_basis_method",),
    buckets=(0, 1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000, 10000),
)

RECALCULATION_DEPTH = Histogram(
    "recalculation_depth",
    "Number of historical transactions replayed during a single cost basis recalculation.",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
)

RECALCULATION_DURATION_SECONDS = Histogram(
    "recalculation_duration_seconds",
    "Wall-clock time spent inside the cost calculator recalculation process.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
