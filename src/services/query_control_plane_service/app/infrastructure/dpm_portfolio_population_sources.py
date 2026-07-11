"""SQLAlchemy adapter for approved models and DPM mandate populations."""

from datetime import date
from typing import Any

from portfolio_common.database_models import ModelPortfolioDefinition, PortfolioMandateBinding
from portfolio_common.source_lifecycle_predicates import (
    DISCRETIONARY_MANDATE_TYPE,
    DPM_DISCRETIONARY_MANDATE_ACTIVE,
)
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.dpm_portfolio_population import (
    ApprovedModelPortfolio,
    DiscretionaryMandatePopulationMember,
)
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyDpmPortfolioPopulationReader:
    """Select approved models and deterministic effective mandate populations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_approved_model(
        self, *, model_portfolio_id: str, as_of_date: date
    ) -> ApprovedModelPortfolio | None:
        statement = (
            select(ModelPortfolioDefinition)
            .where(
                ModelPortfolioDefinition.model_portfolio_id == model_portfolio_id,
                ModelPortfolioDefinition.approval_status == "approved",
                effective_on(
                    ModelPortfolioDefinition.effective_from,
                    ModelPortfolioDefinition.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                ModelPortfolioDefinition.effective_from.desc(),
                ModelPortfolioDefinition.approved_at.desc().nulls_last(),
                ModelPortfolioDefinition.updated_at.desc(),
            )
            .limit(1)
        )
        result = await self._session.execute(statement)
        row = result.scalars().first()
        return _approved_model(row) if row is not None else None

    async def list_affected_mandates(
        self,
        *,
        model_portfolio_id: str,
        as_of_date: date,
        booking_center_code: str | None,
        include_inactive_mandates: bool,
    ) -> list[DiscretionaryMandatePopulationMember]:
        predicates = _mandate_predicates(
            as_of_date=as_of_date,
            booking_center_code=booking_center_code,
            model_portfolio_ids=(model_portfolio_id,),
            include_inactive_mandates=include_inactive_mandates,
        )
        rows = await self._list_ranked_mandates(predicates=predicates)
        return [_mandate_member(row) for row in rows]

    async def list_universe_candidates(
        self,
        *,
        as_of_date: date,
        booking_center_code: str | None,
        model_portfolio_ids: tuple[str, ...],
        include_inactive_mandates: bool,
        after_sort_key: tuple[str, str] | None,
        limit: int,
    ) -> list[DiscretionaryMandatePopulationMember]:
        predicates = _mandate_predicates(
            as_of_date=as_of_date,
            booking_center_code=booking_center_code,
            model_portfolio_ids=model_portfolio_ids,
            include_inactive_mandates=include_inactive_mandates,
        )
        rows = await self._list_ranked_mandates(
            predicates=predicates,
            after_sort_key=after_sort_key,
            limit=limit,
        )
        return [_mandate_member(row) for row in rows]

    async def _list_ranked_mandates(
        self,
        *,
        predicates: list[Any],
        after_sort_key: tuple[str, str] | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        ranked = ranked_latest_ids(
            PortfolioMandateBinding,
            PortfolioMandateBinding.portfolio_id,
            PortfolioMandateBinding.mandate_id,
            predicates=predicates,
            order_by=(
                PortfolioMandateBinding.effective_from.desc(),
                PortfolioMandateBinding.observed_at.desc().nullslast(),
                PortfolioMandateBinding.binding_version.desc(),
                PortfolioMandateBinding.updated_at.desc(),
                PortfolioMandateBinding.created_at.desc(),
                PortfolioMandateBinding.id.desc(),
            ),
        )
        statement = (
            select(PortfolioMandateBinding)
            .join(ranked, PortfolioMandateBinding.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                PortfolioMandateBinding.portfolio_id.asc(),
                PortfolioMandateBinding.mandate_id.asc(),
            )
        )
        if after_sort_key is not None:
            statement = statement.where(
                tuple_(
                    PortfolioMandateBinding.portfolio_id,
                    PortfolioMandateBinding.mandate_id,
                )
                > after_sort_key
            )
        if limit is not None:
            statement = statement.limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())


def _mandate_predicates(
    *,
    as_of_date: date,
    booking_center_code: str | None,
    model_portfolio_ids: tuple[str, ...],
    include_inactive_mandates: bool,
) -> list[Any]:
    predicates = [
        PortfolioMandateBinding.mandate_type == DISCRETIONARY_MANDATE_TYPE,
        effective_on(
            PortfolioMandateBinding.effective_from,
            PortfolioMandateBinding.effective_to,
            as_of_date,
        ),
    ]
    if booking_center_code:
        predicates.append(PortfolioMandateBinding.booking_center_code == booking_center_code)
    if model_portfolio_ids:
        predicates.append(PortfolioMandateBinding.model_portfolio_id.in_(model_portfolio_ids))
    if not include_inactive_mandates:
        predicates.append(
            DPM_DISCRETIONARY_MANDATE_ACTIVE.sqlalchemy_filter(
                PortfolioMandateBinding.discretionary_authority_status
            )
        )
    return predicates


def _approved_model(row: Any) -> ApprovedModelPortfolio:
    return ApprovedModelPortfolio(
        model_portfolio_id=row.model_portfolio_id,
        model_portfolio_version=row.model_portfolio_version,
        approval_status=row.approval_status,
        approved_at=row.approved_at,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        source_system=row.source_system,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _mandate_member(row: Any) -> DiscretionaryMandatePopulationMember:
    return DiscretionaryMandatePopulationMember(
        portfolio_id=row.portfolio_id,
        mandate_id=row.mandate_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        jurisdiction_code=row.jurisdiction_code,
        discretionary_authority_status=row.discretionary_authority_status,
        model_portfolio_id=row.model_portfolio_id,
        policy_pack_id=row.policy_pack_id,
        mandate_objective=row.mandate_objective,
        risk_profile=row.risk_profile,
        investment_horizon=row.investment_horizon,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=int(row.binding_version),
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
