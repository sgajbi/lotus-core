from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from ..dtos.reference_integration_dto import (
    ClassificationTaxonomyResponse,
    CoverageResponse,
)
from .benchmark_coverage import resolve_benchmark_coverage_response
from .classification_taxonomy import resolve_classification_taxonomy_response
from .risk_free_coverage import resolve_risk_free_coverage_response


@dataclass(frozen=True)
class BenchmarkReferenceIntegrationService:
    """Contract-family service for benchmark and market reference products."""

    reference_repository_provider: Callable[[], Any]

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        return cast(
            CoverageResponse,
            await resolve_benchmark_coverage_response(
                repository=self.reference_repository_provider(),
                benchmark_id=benchmark_id,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        return cast(
            CoverageResponse,
            await resolve_risk_free_coverage_response(
                repository=self.reference_repository_provider(),
                currency=currency,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        return cast(
            ClassificationTaxonomyResponse,
            await resolve_classification_taxonomy_response(
                repository=self.reference_repository_provider(),
                as_of_date=as_of_date,
                taxonomy_scope=taxonomy_scope,
            ),
        )
