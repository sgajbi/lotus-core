"""SQLAlchemy adapter for canonical risk-free series windows."""

from datetime import date
from typing import Any

from portfolio_common.database_models import RiskFreeSeries
from portfolio_common.domain.currency import normalize_currency_code
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.risk_free_series import RiskFreeRateEvidence
from .canonical_series_queries import canonical_series_ids


class SqlAlchemyRiskFreeSeriesReader:
    """Select one deterministic risk-free source row per currency and business date."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_rates(
        self, *, currency: str, start_date: date, end_date: date
    ) -> list[RiskFreeRateEvidence]:
        normalized_currency = normalize_currency_code(currency)
        predicates = (
            RiskFreeSeries.series_currency == normalized_currency,
            RiskFreeSeries.series_date >= start_date,
            RiskFreeSeries.series_date <= end_date,
        )
        ranked = canonical_series_ids(
            RiskFreeSeries,
            RiskFreeSeries.series_date,
            predicates=predicates,
        )
        statement = (
            select(RiskFreeSeries)
            .join(ranked, RiskFreeSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(RiskFreeSeries.series_date.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_evidence(row) for row in rows]


def _to_evidence(row: Any) -> RiskFreeRateEvidence:
    return RiskFreeRateEvidence(
        series_id=row.series_id,
        risk_free_curve_id=row.risk_free_curve_id,
        series_date=row.series_date,
        value=row.value,
        value_convention=row.value_convention,
        day_count_convention=row.day_count_convention,
        compounding_convention=row.compounding_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
        observed_at=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
