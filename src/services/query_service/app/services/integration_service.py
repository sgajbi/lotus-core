from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reference_integration_dto import (
    ClassificationTaxonomyResponse,
    CoverageResponse,
)
from ..repositories.reference_data_repository import ReferenceDataRepository
from .benchmark_reference_integration_service import BenchmarkReferenceIntegrationService


@dataclass(frozen=True)
class IntegrationServiceDependencies:
    reference_repository: ReferenceDataRepository

    @classmethod
    def from_session(cls, db: AsyncSession) -> "IntegrationServiceDependencies":
        return cls(reference_repository=ReferenceDataRepository(db))


class IntegrationService:
    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        dependencies: IntegrationServiceDependencies | None = None,
    ):
        if dependencies is None:
            if db is None:
                raise ValueError("IntegrationService requires db or dependencies")
            dependencies = IntegrationServiceDependencies.from_session(db)
        self.db = db
        self._reference_repository = dependencies.reference_repository
        self._benchmark_reference_service = BenchmarkReferenceIntegrationService(
            reference_repository_provider=lambda: self._reference_repository,
        )

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        return await self._benchmark_reference_service.get_benchmark_coverage(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        return await self._benchmark_reference_service.get_risk_free_coverage(
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        return await self._benchmark_reference_service.get_classification_taxonomy(
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
        )
