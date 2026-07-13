"""SQLAlchemy adapter for effective benchmark definition evidence."""

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import BenchmarkCompositionSeries, BenchmarkDefinition
from portfolio_common.domain.currency import normalize_currency_code
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

    async def list_component_index_ids_page(
        self,
        *,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        after_index_id: str | None,
        limit: int,
    ) -> list[str]:
        predicates = [
            BenchmarkCompositionSeries.benchmark_id == benchmark_id.strip(),
            BenchmarkCompositionSeries.composition_effective_from <= end_date,
            or_(
                BenchmarkCompositionSeries.composition_effective_to.is_(None),
                BenchmarkCompositionSeries.composition_effective_to >= start_date,
            ),
        ]
        if after_index_id:
            predicates.append(BenchmarkCompositionSeries.index_id > after_index_id.strip())
        statement = (
            select(BenchmarkCompositionSeries.index_id)
            .where(*predicates)
            .distinct()
            .order_by(BenchmarkCompositionSeries.index_id.asc())
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def list_components_for_indices_overlapping_window(
        self,
        *,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        index_ids: list[str],
    ) -> list[BenchmarkComponentEvidence]:
        canonical_ids = list(
            dict.fromkeys(index_id.strip() for index_id in index_ids if index_id.strip())
        )
        if not canonical_ids:
            return []
        statement = (
            select(BenchmarkCompositionSeries)
            .where(
                BenchmarkCompositionSeries.benchmark_id == benchmark_id.strip(),
                BenchmarkCompositionSeries.index_id.in_(canonical_ids),
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

    async def list_definitions(
        self,
        *,
        as_of_date: date,
        benchmark_type: str | None,
        benchmark_currency: str | None,
        benchmark_status: str | None,
    ) -> list[BenchmarkDefinitionEvidence]:
        predicates = [
            effective_on(
                BenchmarkDefinition.effective_from,
                BenchmarkDefinition.effective_to,
                as_of_date,
            )
        ]
        if benchmark_type:
            predicates.append(BenchmarkDefinition.benchmark_type == benchmark_type.strip().lower())
        if benchmark_currency:
            predicates.append(
                BenchmarkDefinition.benchmark_currency
                == normalize_currency_code(benchmark_currency)
            )
        if benchmark_status:
            predicates.append(
                BenchmarkDefinition.benchmark_status == benchmark_status.strip().lower()
            )
        ranked = ranked_latest_ids(
            BenchmarkDefinition,
            BenchmarkDefinition.benchmark_id,
            predicates=predicates,
            order_by=(
                BenchmarkDefinition.effective_from.desc(),
                BenchmarkDefinition.source_timestamp.desc().nulls_last(),
                BenchmarkDefinition.updated_at.desc(),
                BenchmarkDefinition.created_at.desc(),
                BenchmarkDefinition.id.desc(),
            ),
        )
        statement = (
            select(BenchmarkDefinition)
            .join(ranked, BenchmarkDefinition.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkDefinition.benchmark_id.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_definition_evidence(row) for row in rows]

    async def list_components_for_benchmarks(
        self, *, benchmark_ids: list[str], as_of_date: date
    ) -> dict[str, list[BenchmarkComponentEvidence]]:
        if not benchmark_ids:
            return {}
        predicates = [
            BenchmarkCompositionSeries.benchmark_id.in_(benchmark_ids),
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
            .order_by(
                BenchmarkCompositionSeries.benchmark_id.asc(),
                BenchmarkCompositionSeries.index_id.asc(),
            )
        )
        rows = (await self._session.execute(statement)).scalars().all()
        grouped: dict[str, list[BenchmarkComponentEvidence]] = {}
        for row in rows:
            grouped.setdefault(row.benchmark_id, []).append(_component_evidence(row))
        return grouped


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
