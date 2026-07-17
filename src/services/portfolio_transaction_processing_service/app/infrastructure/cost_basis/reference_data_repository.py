"""SQLAlchemy adapter for cost-basis portfolio and instrument reference data."""

from portfolio_common.database_models import Instrument, Portfolio
from portfolio_common.domain.cost_basis_method import normalize_cost_basis_method
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...ports import (
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
    CostBasisReferenceData,
)


class SqlAlchemyCostBasisReferenceDataRepository:
    """Map persisted reference rows to framework-neutral cost-basis records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_cost_basis_reference_data(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> CostBasisReferenceData | None:
        """Load both reference owners in one round trip for the processing hot path."""

        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(
                Portfolio.portfolio_id.label("portfolio_id"),
                Portfolio.base_currency.label("base_currency"),
                Portfolio.cost_basis_method.label("cost_basis_method"),
                Instrument.security_id.label("instrument_security_id"),
                Instrument.product_type.label("instrument_product_type"),
                Instrument.asset_class.label("instrument_asset_class"),
            )
            .select_from(Portfolio)
            .outerjoin(
                Instrument,
                func.trim(Instrument.security_id) == normalized_security_id,
            )
            .where(Portfolio.portfolio_id == portfolio_id)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).mappings().first()
        if row is None:
            return None

        instrument_security_id = row["instrument_security_id"]
        instrument = (
            None
            if instrument_security_id is None
            else CostBasisInstrumentReference(
                security_id=instrument_security_id,
                product_type=row["instrument_product_type"],
                asset_class=row["instrument_asset_class"],
            )
        )
        return CostBasisReferenceData(
            portfolio=CostBasisPortfolioReference(
                portfolio_id=row["portfolio_id"],
                base_currency=row["base_currency"],
                cost_basis_method=normalize_cost_basis_method(row["cost_basis_method"]),
            ),
            instrument=instrument,
        )
