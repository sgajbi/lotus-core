"""SQLAlchemy adapter for cost-basis portfolio and instrument reference data."""

from typing import cast

from portfolio_common.database_models import Instrument, Portfolio
from portfolio_common.domain.cost_basis_method import normalize_cost_basis_method
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...ports import CostBasisInstrumentReference, CostBasisPortfolioReference


class SqlAlchemyCostBasisReferenceDataRepository:
    """Map persisted reference rows to framework-neutral cost-basis records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_cost_basis_portfolio(
        self, portfolio_id: str
    ) -> CostBasisPortfolioReference | None:
        stmt = select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        result = await self._session.execute(stmt)
        portfolio = result.scalars().first()
        if portfolio is None:
            return None
        return CostBasisPortfolioReference(
            portfolio_id=cast(str, portfolio.portfolio_id),
            base_currency=cast(str, portfolio.base_currency),
            cost_basis_method=normalize_cost_basis_method(portfolio.cost_basis_method),
        )

    async def get_cost_basis_instrument(
        self, security_id: str
    ) -> CostBasisInstrumentReference | None:
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = select(Instrument).where(func.trim(Instrument.security_id) == normalized_security_id)
        result = await self._session.execute(stmt)
        instrument = result.scalars().first()
        if instrument is None:
            return None
        return CostBasisInstrumentReference(
            security_id=cast(str, instrument.security_id),
            product_type=cast(str, instrument.product_type),
            asset_class=cast(str | None, instrument.asset_class),
        )
