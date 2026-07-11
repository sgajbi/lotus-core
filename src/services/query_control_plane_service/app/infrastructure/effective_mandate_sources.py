"""Shared SQL selection for effective discretionary mandate identity."""

from datetime import date

from portfolio_common.database_models import PortfolioMandateBinding
from portfolio_common.source_lifecycle_predicates import DISCRETIONARY_MANDATE_TYPE
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.effective_mandate import EffectiveMandateBinding


async def resolve_effective_mandate_binding(
    session: AsyncSession,
    *,
    portfolio_id: str,
    as_of_date: date,
    mandate_id: str | None,
) -> EffectiveMandateBinding | None:
    """Resolve the highest-precedence discretionary mandate effective on a business date."""

    statement = (
        select(PortfolioMandateBinding)
        .where(
            PortfolioMandateBinding.portfolio_id == portfolio_id,
            PortfolioMandateBinding.mandate_type == DISCRETIONARY_MANDATE_TYPE,
            and_(
                PortfolioMandateBinding.effective_from <= as_of_date,
                or_(
                    PortfolioMandateBinding.effective_to.is_(None),
                    PortfolioMandateBinding.effective_to >= as_of_date,
                ),
            ),
        )
        .order_by(
            PortfolioMandateBinding.effective_from.desc(),
            PortfolioMandateBinding.observed_at.desc().nulls_last(),
            PortfolioMandateBinding.binding_version.desc(),
            PortfolioMandateBinding.updated_at.desc(),
        )
        .limit(1)
    )
    if mandate_id:
        statement = statement.where(PortfolioMandateBinding.mandate_id == mandate_id)
    result = await session.execute(statement)
    row = result.scalars().first()
    if row is None:
        return None
    return EffectiveMandateBinding(
        client_id=row.client_id,
        mandate_id=row.mandate_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
