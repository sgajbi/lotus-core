from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import BenchmarkCatalogResponse
from .reference_data_mappers import benchmark_definition_response


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
