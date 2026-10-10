from typing import NoReturn

from fastapi import status

from .response_helpers import problem_example, problem_response, raise_problem

BENCHMARK_MARKET_SERIES_DESCRIPTION = (
    "What: Return benchmark market series inputs required by lotus-performance.\n"
    "How: Resolves components and returns aligned raw series honoring requested "
    "series_fields, deterministic paging, and benchmark-to-target FX context semantics.\n"
    "When: Used by lotus-performance and other downstream benchmark sourcing workflows that "
    "need native component series plus benchmark-to-target FX context. The response "
    "publishes native component series plus optional benchmark-to-target FX context; "
    "lotus-performance owns benchmark math and any benchmark-currency normalization of "
    "component series. An effective benchmark definition is required for every request; "
    "missing definitions refuse with HTTP 409 before component or FX reads. The requested "
    "target currency never supplies benchmark base-currency authority."
)
BENCHMARK_MARKET_SERIES_UNAVAILABLE_DETAIL = (
    "The effective benchmark definition or requested FX source selection is unavailable "
    "or conflicting."
)
BENCHMARK_MARKET_SERIES_UNAVAILABLE_RESPONSE = problem_response(
    BENCHMARK_MARKET_SERIES_UNAVAILABLE_DETAIL,
    problem_example(
        status_code=status.HTTP_409_CONFLICT,
        title="Market data source selection unavailable",
        detail=BENCHMARK_MARKET_SERIES_UNAVAILABLE_DETAIL,
        error_code="QCP_FX_SOURCE_SELECTION_CONFLICT",
        instance="/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/market-series",
        metadata={
            "source_product": "MarketDataWindow",
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        },
    ),
)


def raise_benchmark_market_source_unavailable(benchmark_id: str) -> NoReturn:
    raise_problem(
        status_code=status.HTTP_409_CONFLICT,
        title="Market data source selection unavailable",
        detail=BENCHMARK_MARKET_SERIES_UNAVAILABLE_DETAIL,
        error_code="QCP_FX_SOURCE_SELECTION_CONFLICT",
        metadata={"source_product": "MarketDataWindow", "benchmark_id": benchmark_id},
    )
