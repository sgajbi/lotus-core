"""SQLAlchemy adapter for dated market FX evidence."""

from datetime import date
from typing import Any

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.database_models import FxRate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.market_fx import FxRateEvidence


class SqlAlchemyMarketFxRateReader:
    """Read normalized currency-pair rates in deterministic date order."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_rates(
        self,
        *,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> list[FxRateEvidence]:
        normalized_from = normalize_currency_code(from_currency)
        normalized_to = normalize_currency_code(to_currency)
        statement = (
            select(FxRate)
            .where(
                func.upper(func.trim(FxRate.from_currency)) == normalized_from,
                func.upper(func.trim(FxRate.to_currency)) == normalized_to,
                FxRate.rate_date >= start_date,
                FxRate.rate_date <= end_date,
            )
            .order_by(FxRate.rate_date.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_evidence(row) for row in rows]


def _to_evidence(row: Any) -> FxRateEvidence:
    return FxRateEvidence(
        from_currency=normalize_currency_code(row.from_currency),
        to_currency=normalize_currency_code(row.to_currency),
        rate_date=row.rate_date,
        rate=row.rate,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
