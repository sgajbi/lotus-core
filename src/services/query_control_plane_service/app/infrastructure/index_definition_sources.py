"""SQLAlchemy adapter for effective index definition evidence."""

from datetime import date
from typing import Any

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.database_models import IndexDefinition
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.index_definition import IndexDefinitionEvidence
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyIndexDefinitionReader:
    """Select one deterministic effective record per canonical index."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_definitions(
        self,
        *,
        as_of_date: date,
        index_ids: list[str],
        index_currency: str | None,
        index_type: str | None,
        index_status: str | None,
    ) -> list[IndexDefinitionEvidence]:
        normalized_ids = list(dict.fromkeys(value.strip() for value in index_ids if value.strip()))
        predicates = [
            effective_on(IndexDefinition.effective_from, IndexDefinition.effective_to, as_of_date)
        ]
        if normalized_ids:
            predicates.append(IndexDefinition.index_id.in_(normalized_ids))
        if index_currency:
            predicates.append(
                IndexDefinition.index_currency == normalize_currency_code(index_currency)
            )
        if index_type:
            predicates.append(IndexDefinition.index_type == index_type.strip().lower())
        if index_status:
            predicates.append(IndexDefinition.index_status == index_status.strip().lower())
        ranked = ranked_latest_ids(
            IndexDefinition,
            IndexDefinition.index_id,
            predicates=predicates,
            order_by=(
                IndexDefinition.effective_from.desc(),
                IndexDefinition.source_timestamp.desc().nulls_last(),
                IndexDefinition.updated_at.desc(),
                IndexDefinition.created_at.desc(),
                IndexDefinition.id.desc(),
            ),
        )
        statement = (
            select(IndexDefinition)
            .join(ranked, IndexDefinition.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexDefinition.index_id.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_evidence(row) for row in rows]


def _to_evidence(row: Any) -> IndexDefinitionEvidence:
    return IndexDefinitionEvidence(
        index_id=row.index_id,
        index_name=row.index_name,
        index_currency=row.index_currency,
        index_type=row.index_type,
        index_status=row.index_status,
        index_provider=row.index_provider,
        index_market=row.index_market,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
