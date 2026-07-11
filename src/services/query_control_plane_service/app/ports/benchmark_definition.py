"""Read port for effective benchmark definitions and constituents."""

from datetime import date
from typing import Protocol

from ..domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)


class BenchmarkDefinitionReader(Protocol):
    """Read benchmark master and constituent evidence without persistence leakage."""

    async def resolve_definition(
        self, *, benchmark_id: str, as_of_date: date
    ) -> BenchmarkDefinitionEvidence | None: ...

    async def list_components(
        self, *, benchmark_id: str, as_of_date: date
    ) -> list[BenchmarkComponentEvidence]: ...

    async def list_definitions_overlapping_window(
        self, *, benchmark_id: str, start_date: date, end_date: date
    ) -> list[BenchmarkDefinitionEvidence]: ...

    async def list_components_overlapping_window(
        self, *, benchmark_id: str, start_date: date, end_date: date
    ) -> list[BenchmarkComponentEvidence]: ...

    async def list_component_index_ids_page(
        self,
        *,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        after_index_id: str | None,
        limit: int,
    ) -> list[str]: ...

    async def list_components_for_indices_overlapping_window(
        self,
        *,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        index_ids: list[str],
    ) -> list[BenchmarkComponentEvidence]: ...

    async def list_definitions(
        self,
        *,
        as_of_date: date,
        benchmark_type: str | None,
        benchmark_currency: str | None,
        benchmark_status: str | None,
    ) -> list[BenchmarkDefinitionEvidence]: ...

    async def list_components_for_benchmarks(
        self, *, benchmark_ids: list[str], as_of_date: date
    ) -> dict[str, list[BenchmarkComponentEvidence]]: ...
