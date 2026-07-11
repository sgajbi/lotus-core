"""SQLAlchemy adapter for canonical index series windows."""

from datetime import date
from typing import Any

from portfolio_common.database_models import IndexPriceSeries, IndexReturnSeries
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.index_series import IndexPriceEvidence, IndexReturnEvidence
from .canonical_series_queries import canonical_series_ids


class SqlAlchemyIndexSeriesReader:
    """Select one deterministic source row per index and business date."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_prices(
        self, *, index_id: str, start_date: date, end_date: date
    ) -> list[IndexPriceEvidence]:
        canonical_id = index_id.strip()
        predicates = (
            IndexPriceSeries.index_id == canonical_id,
            IndexPriceSeries.series_date >= start_date,
            IndexPriceSeries.series_date <= end_date,
        )
        ranked = canonical_series_ids(
            IndexPriceSeries,
            IndexPriceSeries.index_id,
            IndexPriceSeries.series_date,
            predicates=predicates,
        )
        statement = (
            select(IndexPriceSeries)
            .join(ranked, IndexPriceSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexPriceSeries.series_date.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_price_evidence(row) for row in rows]

    async def list_returns(
        self, *, index_id: str, start_date: date, end_date: date
    ) -> list[IndexReturnEvidence]:
        canonical_id = index_id.strip()
        predicates = (
            IndexReturnSeries.index_id == canonical_id,
            IndexReturnSeries.series_date >= start_date,
            IndexReturnSeries.series_date <= end_date,
        )
        ranked = canonical_series_ids(
            IndexReturnSeries,
            IndexReturnSeries.index_id,
            IndexReturnSeries.series_date,
            predicates=predicates,
        )
        statement = (
            select(IndexReturnSeries)
            .join(ranked, IndexReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexReturnSeries.series_date.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_return_evidence(row) for row in rows]


def _price_evidence(row: Any) -> IndexPriceEvidence:
    return IndexPriceEvidence(
        series_id=row.series_id,
        index_id=row.index_id,
        series_date=row.series_date,
        index_price=row.index_price,
        series_currency=row.series_currency,
        value_convention=row.value_convention,
        quality_status=row.quality_status,
        observed_at=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _return_evidence(row: Any) -> IndexReturnEvidence:
    return IndexReturnEvidence(
        series_id=row.series_id,
        index_id=row.index_id,
        series_date=row.series_date,
        index_return=row.index_return,
        return_period=row.return_period,
        return_convention=row.return_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
        observed_at=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
