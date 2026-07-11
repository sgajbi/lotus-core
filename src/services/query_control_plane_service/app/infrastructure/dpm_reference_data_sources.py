"""SQLAlchemy adapter for effective DPM reference-data evidence."""

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.database_models import (
    FxRate,
    InstrumentEligibilityProfile,
    MarketPrice,
    ModelPortfolioDefinition,
    ModelPortfolioTarget,
    PortfolioMandateBinding,
)
from portfolio_common.source_lifecycle_predicates import (
    DISCRETIONARY_MANDATE_TYPE,
    MODEL_PORTFOLIO_TARGET_ACTIVE,
)
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.dpm_source_readiness import (
    DiscretionaryMandateBindingEvidence,
    FxRateEvidence,
    InstrumentEligibilityEvidence,
    MarketPriceEvidence,
    ModelPortfolioDefinitionEvidence,
    ModelPortfolioTargetEvidence,
)
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyDpmReferenceDataReader:
    """Select deterministic reference evidence for DPM readiness policies."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_model_portfolio_definition(
        self,
        *,
        model_portfolio_id: str,
        as_of_date: date,
    ) -> ModelPortfolioDefinitionEvidence | None:
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
        row = (await self._session.execute(statement)).scalars().first()
        return _model_definition(row) if row is not None else None

    async def list_model_portfolio_targets(
        self,
        *,
        model_portfolio_id: str,
        model_portfolio_version: str,
        as_of_date: date,
        include_inactive_targets: bool,
    ) -> list[ModelPortfolioTargetEvidence]:
        predicates = [
            ModelPortfolioTarget.model_portfolio_id == model_portfolio_id,
            ModelPortfolioTarget.model_portfolio_version == model_portfolio_version,
            effective_on(
                ModelPortfolioTarget.effective_from,
                ModelPortfolioTarget.effective_to,
                as_of_date,
            ),
        ]
        if not include_inactive_targets:
            predicates.append(
                MODEL_PORTFOLIO_TARGET_ACTIVE.sqlalchemy_filter(ModelPortfolioTarget.target_status)
            )
        ranked = ranked_latest_ids(
            ModelPortfolioTarget,
            ModelPortfolioTarget.model_portfolio_id,
            ModelPortfolioTarget.model_portfolio_version,
            ModelPortfolioTarget.instrument_id,
            predicates=predicates,
            order_by=(
                ModelPortfolioTarget.effective_from.desc(),
                ModelPortfolioTarget.updated_at.desc(),
                ModelPortfolioTarget.created_at.desc(),
                ModelPortfolioTarget.id.desc(),
            ),
        )
        statement = (
            select(ModelPortfolioTarget)
            .join(ranked, ModelPortfolioTarget.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(ModelPortfolioTarget.instrument_id.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_model_target(row) for row in rows]

    async def resolve_discretionary_mandate_binding(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        mandate_id: str | None,
        booking_center_code: str | None,
    ) -> DiscretionaryMandateBindingEvidence | None:
        statement = (
            select(PortfolioMandateBinding)
            .where(
                PortfolioMandateBinding.portfolio_id == portfolio_id,
                PortfolioMandateBinding.mandate_type == DISCRETIONARY_MANDATE_TYPE,
                effective_on(
                    PortfolioMandateBinding.effective_from,
                    PortfolioMandateBinding.effective_to,
                    as_of_date,
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
        if booking_center_code:
            statement = statement.where(
                PortfolioMandateBinding.booking_center_code == booking_center_code
            )
        row = (await self._session.execute(statement)).scalars().first()
        return _mandate_binding(row) if row is not None else None

    async def list_instrument_eligibility_profiles(
        self,
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[InstrumentEligibilityEvidence]:
        normalized_ids = _normalized_security_ids(security_ids)
        if not normalized_ids:
            return []
        security_id = func.trim(InstrumentEligibilityProfile.security_id)
        predicates = [
            security_id.in_(normalized_ids),
            effective_on(
                InstrumentEligibilityProfile.effective_from,
                InstrumentEligibilityProfile.effective_to,
                as_of_date,
            ),
        ]
        ranked = ranked_latest_ids(
            InstrumentEligibilityProfile,
            security_id,
            predicates=predicates,
            order_by=(
                InstrumentEligibilityProfile.effective_from.desc(),
                InstrumentEligibilityProfile.observed_at.desc().nulls_last(),
                InstrumentEligibilityProfile.eligibility_version.desc(),
                InstrumentEligibilityProfile.updated_at.desc(),
                InstrumentEligibilityProfile.created_at.desc(),
                InstrumentEligibilityProfile.id.desc(),
            ),
        )
        statement = (
            select(InstrumentEligibilityProfile)
            .join(ranked, InstrumentEligibilityProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(security_id.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_instrument_eligibility(row) for row in rows]

    async def list_latest_market_prices(
        self,
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[MarketPriceEvidence]:
        normalized_ids = _normalized_security_ids(security_ids)
        if not normalized_ids:
            return []
        security_id = func.trim(MarketPrice.security_id)
        latest_dates = (
            select(
                security_id.label("security_id"),
                func.max(MarketPrice.price_date).label("latest_price_date"),
            )
            .where(security_id.in_(normalized_ids), MarketPrice.price_date <= as_of_date)
            .group_by(security_id)
            .subquery()
        )
        statement = (
            select(MarketPrice)
            .join(
                latest_dates,
                and_(
                    security_id == latest_dates.c.security_id,
                    MarketPrice.price_date == latest_dates.c.latest_price_date,
                ),
            )
            .order_by(security_id.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_market_price(row) for row in rows]

    async def list_latest_fx_rates(
        self,
        *,
        currency_pairs: list[tuple[str, str]],
        as_of_date: date,
    ) -> list[FxRateEvidence]:
        normalized_pairs = _normalized_currency_pairs(currency_pairs)
        if not normalized_pairs:
            return []
        from_currency = func.upper(func.trim(FxRate.from_currency))
        to_currency = func.upper(func.trim(FxRate.to_currency))
        latest_dates = (
            select(
                from_currency.label("from_currency"),
                to_currency.label("to_currency"),
                func.max(FxRate.rate_date).label("latest_rate_date"),
            )
            .where(
                tuple_(from_currency, to_currency).in_(normalized_pairs),
                FxRate.rate_date <= as_of_date,
            )
            .group_by(from_currency, to_currency)
            .subquery()
        )
        statement = (
            select(FxRate)
            .join(
                latest_dates,
                and_(
                    from_currency == latest_dates.c.from_currency,
                    to_currency == latest_dates.c.to_currency,
                    FxRate.rate_date == latest_dates.c.latest_rate_date,
                ),
            )
            .order_by(from_currency.asc(), to_currency.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_fx_rate(row) for row in rows]


def _normalized_security_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _normalized_currency_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return list(
        dict.fromkeys(
            (normalize_currency_code(base), normalize_currency_code(quote))
            for base, quote in values
        )
    )


def _model_definition(row: Any) -> ModelPortfolioDefinitionEvidence:
    return ModelPortfolioDefinitionEvidence(
        model_portfolio_id=row.model_portfolio_id,
        model_portfolio_version=row.model_portfolio_version,
        display_name=row.display_name,
        base_currency=row.base_currency,
        risk_profile=row.risk_profile,
        mandate_type=row.mandate_type,
        rebalance_frequency=row.rebalance_frequency,
        approval_status=row.approval_status,
        approved_at=row.approved_at,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        source_system=row.source_system,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        quality_status=row.quality_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _model_target(row: Any) -> ModelPortfolioTargetEvidence:
    return ModelPortfolioTargetEvidence(
        instrument_id=row.instrument_id,
        target_weight=Decimal(str(row.target_weight)),
        min_weight=Decimal(str(row.min_weight)) if row.min_weight is not None else None,
        max_weight=Decimal(str(row.max_weight)) if row.max_weight is not None else None,
        target_status=row.target_status,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        source_system=row.source_system,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        quality_status=row.quality_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _mandate_binding(row: Any) -> DiscretionaryMandateBindingEvidence:
    return DiscretionaryMandateBindingEvidence(
        portfolio_id=row.portfolio_id,
        mandate_id=row.mandate_id,
        client_id=row.client_id,
        mandate_type=row.mandate_type,
        discretionary_authority_status=row.discretionary_authority_status,
        booking_center_code=row.booking_center_code,
        jurisdiction_code=row.jurisdiction_code,
        model_portfolio_id=row.model_portfolio_id,
        policy_pack_id=row.policy_pack_id,
        mandate_objective=row.mandate_objective,
        risk_profile=row.risk_profile,
        investment_horizon=row.investment_horizon,
        review_cadence=row.review_cadence,
        last_review_date=row.last_review_date,
        next_review_due_date=row.next_review_due_date,
        leverage_allowed=bool(row.leverage_allowed),
        tax_awareness_allowed=bool(row.tax_awareness_allowed),
        settlement_awareness_required=bool(row.settlement_awareness_required),
        rebalance_frequency=row.rebalance_frequency,
        rebalance_bands=dict(row.rebalance_bands or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=int(row.binding_version),
        source_system=row.source_system,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        quality_status=row.quality_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _instrument_eligibility(row: Any) -> InstrumentEligibilityEvidence:
    return InstrumentEligibilityEvidence(
        security_id=row.security_id.strip(),
        eligibility_status=row.eligibility_status,
        product_shelf_status=row.product_shelf_status,
        buy_allowed=bool(row.buy_allowed),
        sell_allowed=bool(row.sell_allowed),
        restriction_reason_codes=tuple(row.restriction_reason_codes or ()),
        settlement_days=int(row.settlement_days),
        settlement_calendar_id=row.settlement_calendar_id,
        liquidity_tier=row.liquidity_tier,
        issuer_id=row.issuer_id,
        issuer_name=row.issuer_name,
        ultimate_parent_issuer_id=row.ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=row.ultimate_parent_issuer_name,
        asset_class=row.asset_class,
        country_of_risk=row.country_of_risk,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        eligibility_version=int(row.eligibility_version),
        source_system=row.source_system,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        quality_status=row.quality_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _market_price(row: Any) -> MarketPriceEvidence:
    return MarketPriceEvidence(
        security_id=row.security_id.strip(),
        price_date=row.price_date,
        price=Decimal(str(row.price)),
        currency=row.currency,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _fx_rate(row: Any) -> FxRateEvidence:
    return FxRateEvidence(
        from_currency=normalize_currency_code(row.from_currency),
        to_currency=normalize_currency_code(row.to_currency),
        rate_date=row.rate_date,
        rate=Decimal(str(row.rate)),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
