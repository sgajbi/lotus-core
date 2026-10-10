"""SQLAlchemy adapter for effective classification taxonomy evidence."""

from datetime import date
from typing import Any

from portfolio_common.api_contract.classification_history import (
    ClassificationHistorySelection,
    RetainedClassificationCut,
)
from portfolio_common.database_models import ClassificationTaxonomy
from portfolio_common.reference_classification_schema import InstrumentClassificationCutRecord
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.classification_taxonomy import ClassificationTaxonomyEvidence
from .effective_profile_queries import effective_on


class SqlAlchemyClassificationTaxonomyReader:
    """Select effective taxonomy labels in deterministic domain order."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_cut(
        self, selection: ClassificationHistorySelection
    ) -> RetainedClassificationCut | None:
        model = InstrumentClassificationCutRecord
        row = (
            await self._session.execute(
                select(model).where(
                    model.cut_id == selection.cut_id,
                    model.content_hash == selection.content_hash,
                    model.producer_id == selection.producer_id,
                    model.classification_set_id == selection.classification_set_id,
                    model.source_record_id == selection.source_record_id,
                    model.source_version == selection.source_version,
                    model.received_at <= selection.known_at,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        try:
            return RetainedClassificationCut(
                cut_id=row.cut_id,
                content_hash=row.content_hash,
                received_at=row.received_at,
                source=row.payload,
            )
        except ValidationError:
            # Invalid custody is unavailable; it cannot become current enrichment.
            return None

    async def list_effective(
        self, *, as_of_date: date, taxonomy_scope: str | None
    ) -> list[ClassificationTaxonomyEvidence]:
        statement = select(ClassificationTaxonomy).where(
            effective_on(
                ClassificationTaxonomy.effective_from,
                ClassificationTaxonomy.effective_to,
                as_of_date,
            )
        )
        if taxonomy_scope:
            statement = statement.where(ClassificationTaxonomy.taxonomy_scope == taxonomy_scope)
        statement = statement.order_by(
            ClassificationTaxonomy.taxonomy_scope.asc(),
            ClassificationTaxonomy.dimension_name.asc(),
            ClassificationTaxonomy.dimension_value.asc(),
            ClassificationTaxonomy.effective_from.asc(),
            ClassificationTaxonomy.id.asc(),
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_evidence(row) for row in rows]


def _to_evidence(row: Any) -> ClassificationTaxonomyEvidence:
    return ClassificationTaxonomyEvidence(
        classification_set_id=row.classification_set_id,
        taxonomy_scope=row.taxonomy_scope,
        dimension_name=row.dimension_name,
        dimension_value=row.dimension_value,
        dimension_description=row.dimension_description,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        observed_at=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
