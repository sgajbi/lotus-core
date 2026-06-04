from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import BenchmarkCatalogResponse
from .reference_data_mappers import benchmark_definition_response


async def resolve_benchmark_catalog_response(
    *,
    repository: Any,
    as_of_date: date,
    benchmark_type: str | None,
    benchmark_currency: str | None,
    benchmark_status: str | None,
) -> BenchmarkCatalogResponse:
    rows = await repository.list_benchmark_definitions(
        as_of_date=as_of_date,
        benchmark_type=benchmark_type,
        benchmark_currency=benchmark_currency,
        benchmark_status=benchmark_status,
    )
    components_by_benchmark = await repository.list_benchmark_components_for_benchmarks(
        benchmark_ids=[row.benchmark_id for row in rows],
        as_of_date=as_of_date,
    )
    return build_benchmark_catalog_response(
        as_of_date=as_of_date,
        rows=rows,
        components_by_benchmark=components_by_benchmark,
    )


def build_benchmark_catalog_response(
    *,
    as_of_date: date,
    rows: list[Any],
    components_by_benchmark: dict[str, list[Any]],
) -> BenchmarkCatalogResponse:
    return BenchmarkCatalogResponse(
        as_of_date=as_of_date,
        records=[
            benchmark_definition_response(
                row,
                components=components_by_benchmark.get(row.benchmark_id, []),
            )
            for row in rows
        ],
    )
