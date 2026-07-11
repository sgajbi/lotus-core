"""SQLAlchemy adapter for effective benchmark definition evidence."""

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import BenchmarkCompositionSeries, BenchmarkDefinition
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyBenchmarkDefinitionReader:
    """Select deterministic benchmark master and constituent records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_definition(
        self, *, benchmark_id: str, as_of_date: date
    ) -> BenchmarkDefinitionEvidence | None:
        statement = (
            select(BenchmarkDefinition)
            .where(
                BenchmarkDefinition.benchmark_id == benchmark_id,
                effective_on(
                    BenchmarkDefinition.effective_from,
                    BenchmarkDefinition.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                BenchmarkDefinition.effective_from.desc(),
                BenchmarkDefinition.source_timestamp.desc().nulls_last(),
                BenchmarkDefinition.updated_at.desc(),
                BenchmarkDefinition.created_at.desc(),
                BenchmarkDefinition.id.desc(),
            )
            .limit(1)
        )
        row = (await self._session.execute(statement)).scalars().first()
        return _definition_evidence(row) if row is not None else None

    async def list_components(
        self, *, benchmark_id: str, as_of_date: date
    ) -> list[BenchmarkComponentEvidence]:
        predicates = [
            BenchmarkCompositionSeries.benchmark_id == benchmark_id,
            effective_on(
                BenchmarkCompositionSeries.composition_effective_from,
                BenchmarkCompositionSeries.composition_effective_to,
                as_of_date,
            ),
        ]
        ranked = ranked_latest_ids(
            BenchmarkCompositionSeries,
            BenchmarkCompositionSeries.benchmark_id,
            BenchmarkCompositionSeries.index_id,
            predicates=predicates,
            order_by=(
                BenchmarkCompositionSeries.composition_effective_from.desc(),
                BenchmarkCompositionSeries.source_timestamp.desc().nulls_last(),
                BenchmarkCompositionSeries.updated_at.desc(),
                BenchmarkCompositionSeries.created_at.desc(),
                BenchmarkCompositionSeries.id.desc(),
            ),
        )
        statement = (
            select(BenchmarkCompositionSeries)
            .join(ranked, BenchmarkCompositionSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkCompositionSeries.index_id.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_component_evidence(row) for row in rows]

    async def list_definitions_overlapping_window(
        self, *, benchmark_id: str, start_date: date, end_date: date
    ) -> list[BenchmarkDefinitionEvidence]:
        statement = (
            select(BenchmarkDefinition)
            .where(
                BenchmarkDefinition.benchmark_id == benchmark_id,
                BenchmarkDefinition.effective_from <= end_date,
                or_(
                    BenchmarkDefinition.effective_to.is_(None),
                    BenchmarkDefinition.effective_to >= start_date,
                ),
            )
            .order_by(
                BenchmarkDefinition.effective_from.asc(),
                BenchmarkDefinition.source_timestamp.asc().nulls_last(),
                BenchmarkDefinition.id.asc(),
            )
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_definition_evidence(row) for row in rows]

    async def list_components_overlapping_window(
        self, *, benchmark_id: str, start_date: date, end_date: date
    ) -> list[BenchmarkComponentEvidence]:
        statement = (
            select(BenchmarkCompositionSeries)
            .where(
                BenchmarkCompositionSeries.benchmark_id == benchmark_id,
                BenchmarkCompositionSeries.composition_effective_from <= end_date,
                or_(
                    BenchmarkCompositionSeries.composition_effective_to.is_(None),
                    BenchmarkCompositionSeries.composition_effective_to >= start_date,
                ),
            )
            .order_by(
                BenchmarkCompositionSeries.index_id.asc(),
                BenchmarkCompositionSeries.composition_effective_from.asc(),
                BenchmarkCompositionSeries.source_timestamp.asc().nulls_last(),
                BenchmarkCompositionSeries.id.asc(),
            )
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_component_evidence(row) for row in rows]


def _definition_evidence(row: Any) -> BenchmarkDefinitionEvidence:
    return BenchmarkDefinitionEvidence(
        benchmark_id=row.benchmark_id,
        benchmark_name=row.benchmark_name,
        benchmark_type=row.benchmark_type,
        benchmark_currency=row.benchmark_currency,
        return_convention=row.return_convention,
        benchmark_status=row.benchmark_status,
        benchmark_family=row.benchmark_family,
        benchmark_provider=row.benchmark_provider,
        rebalance_frequency=row.rebalance_frequency,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        quality_status=row.quality_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _component_evidence(row: Any) -> BenchmarkComponentEvidence:
    return BenchmarkComponentEvidence(
        benchmark_id=row.benchmark_id,
        index_id=row.index_id,
        composition_effective_from=row.composition_effective_from,
        composition_effective_to=row.composition_effective_to,
        composition_weight=Decimal(str(row.composition_weight)),
        rebalance_event_id=row.rebalance_event_id,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        quality_status=row.quality_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
