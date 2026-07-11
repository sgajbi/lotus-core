"""Application facade for Query Service reference taxonomy reads."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reference_integration_dto import ClassificationTaxonomyResponse
from ..repositories.reference_data_repository import ReferenceDataRepository
from .classification_taxonomy import resolve_classification_taxonomy_response


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

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        return await resolve_classification_taxonomy_response(
            repository=self._reference_repository,
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
        )
