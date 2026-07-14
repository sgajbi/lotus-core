"""SQLAlchemy adapter for effective-dated cost-basis FX rates."""

from datetime import date

from portfolio_common.database_models import FxRate
from portfolio_common.domain.currency import normalize_currency_code
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ...domain.cost_basis import EffectiveFxRate


class SqlAlchemyCostBasisFxRateRepository:
    """Load bounded FX windows with one latest-on-or-before seed rate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_fx_rate_window(
        self,
        from_currency: str,
        to_currency: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[EffectiveFxRate]:
        """Return the prior seed and effective rates inside the requested window."""

        if start_date > end_date:
            raise ValueError("FX rate window start_date must be on or before end_date")

        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        from_currency_expr = func.upper(func.trim(FxRate.from_currency))
        to_currency_expr = func.upper(func.trim(FxRate.to_currency))
        prior_rate = aliased(FxRate)
        prior_rate_date = (
            select(func.max(prior_rate.rate_date))
            .where(
                func.upper(func.trim(prior_rate.from_currency)) == normalized_from_currency,
                func.upper(func.trim(prior_rate.to_currency)) == normalized_to_currency,
                prior_rate.rate_date < start_date,
            )
            .scalar_subquery()
        )
        statement = (
            select(FxRate)
            .where(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date <= end_date,
                or_(
                    FxRate.rate_date >= start_date,
                    FxRate.rate_date == prior_rate_date,
                ),
            )
            .order_by(FxRate.rate_date.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [EffectiveFxRate(effective_date=row.rate_date, rate=row.rate) for row in rows]
