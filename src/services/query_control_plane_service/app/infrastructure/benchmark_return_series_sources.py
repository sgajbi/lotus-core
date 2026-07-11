"""SQLAlchemy adapter for canonical benchmark return series windows."""

from datetime import date
from typing import Any

from portfolio_common.database_models import BenchmarkReturnSeries
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.benchmark_return_series import BenchmarkReturnEvidence
from .canonical_series_queries import canonical_series_ids


class SqlAlchemyBenchmarkReturnSeriesReader:
    """Select one deterministic source row per benchmark and business date."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_returns(
        self, *, benchmark_id: str, start_date: date, end_date: date
    ) -> list[BenchmarkReturnEvidence]:
        canonical_id = benchmark_id.strip()
        predicates = (
            BenchmarkReturnSeries.benchmark_id == canonical_id,
            BenchmarkReturnSeries.series_date >= start_date,
            BenchmarkReturnSeries.series_date <= end_date,
        )
        ranked = canonical_series_ids(
            BenchmarkReturnSeries,
            BenchmarkReturnSeries.benchmark_id,
            BenchmarkReturnSeries.series_date,
            predicates=predicates,
        )
        statement = (
            select(BenchmarkReturnSeries)
            .join(ranked, BenchmarkReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkReturnSeries.series_date.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_evidence(row) for row in rows]


def _to_evidence(row: Any) -> BenchmarkReturnEvidence:
    return BenchmarkReturnEvidence(
        series_id=row.series_id,
        benchmark_id=row.benchmark_id,
        series_date=row.series_date,
        benchmark_return=row.benchmark_return,
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
