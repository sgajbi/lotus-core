from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import (
    BenchmarkCompositionSeries,
    BenchmarkDefinition,
    BenchmarkReturnSeries,
    ClassificationTaxonomy,
    ClientIncomeNeedsSchedule,
    ClientRestrictionProfile,
    ClientTaxProfile,
    ClientTaxRuleSet,
    FxRate,
    IndexDefinition,
    IndexPriceSeries,
    IndexReturnSeries,
    InstrumentEligibilityProfile,
    LiquidityReserveRequirement,
    MarketPrice,
    ModelPortfolioDefinition,
    ModelPortfolioTarget,
    PlannedWithdrawalSchedule,
    PortfolioBenchmarkAssignment,
    PortfolioMandateBinding,
    RiskFreeSeries,
    SustainabilityPreferenceProfile,
)
from sqlalchemy import and_, case, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.decimal_amounts import decimal_or_none
from .currency_codes import currency_code_sql_expr, normalize_currency_code
from .identifier_normalization import normalize_security_id
from .reference_coverage_calculations import (
    latest_reference_evidence_timestamp,
    observed_benchmark_coverage_dates,
    quality_status_counts,
)
from .reference_fx_queries import latest_fx_rates_stmt, normalized_currency_pairs


def _effective_filter(
    effective_from_column: Any,
    effective_to_column: Any,
    as_of_date: date,
):
    return and_(
        effective_from_column <= as_of_date,
        or_(effective_to_column.is_(None), effective_to_column >= as_of_date),
    )


def _normalize_reference_status(status: str) -> str:
    return status.strip().lower()


def _canonical_series_ranked_subquery(model: Any, *partition_columns: Any, predicates: Any):
    accepted_quality_rank = case(
        (func.upper(func.trim(model.quality_status)) == "ACCEPTED", 1),
        else_=0,
    )
    return (
        select(
            model.id.label("id"),
            func.row_number()
            .over(
                partition_by=partition_columns,
                order_by=(
                    accepted_quality_rank.desc(),
                    model.source_timestamp.desc().nullslast(),
                    model.series_id.desc(),
                    model.source_vendor.desc().nullslast(),
                    model.source_record_id.desc().nullslast(),
                    model.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


def _ranked_portfolio_mandate_binding_ids(*predicates: Any):
    return (
        select(
            PortfolioMandateBinding.id.label("id"),
            func.row_number()
            .over(
                partition_by=(
                    PortfolioMandateBinding.portfolio_id,
                    PortfolioMandateBinding.mandate_id,
                ),
                order_by=(
                    PortfolioMandateBinding.effective_from.desc(),
                    PortfolioMandateBinding.observed_at.desc().nullslast(),
                    PortfolioMandateBinding.binding_version.desc(),
                    PortfolioMandateBinding.updated_at.desc(),
                    PortfolioMandateBinding.created_at.desc(),
                    PortfolioMandateBinding.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


def _ranked_model_portfolio_target_ids(*predicates: Any):
    return (
        select(
            ModelPortfolioTarget.id.label("id"),
            func.row_number()
            .over(
                partition_by=(
                    ModelPortfolioTarget.model_portfolio_id,
                    ModelPortfolioTarget.model_portfolio_version,
                    ModelPortfolioTarget.instrument_id,
                ),
                order_by=(
                    ModelPortfolioTarget.effective_from.desc(),
                    ModelPortfolioTarget.updated_at.desc(),
                    ModelPortfolioTarget.created_at.desc(),
                    ModelPortfolioTarget.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


def _ranked_instrument_eligibility_ids(security_id_expr: Any, *predicates: Any):
    return (
        select(
            InstrumentEligibilityProfile.id.label("id"),
            func.row_number()
            .over(
                partition_by=security_id_expr,
                order_by=(
                    InstrumentEligibilityProfile.effective_from.desc(),
                    InstrumentEligibilityProfile.observed_at.desc().nullslast(),
                    InstrumentEligibilityProfile.eligibility_version.desc(),
                    InstrumentEligibilityProfile.updated_at.desc(),
                    InstrumentEligibilityProfile.created_at.desc(),
                    InstrumentEligibilityProfile.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


def _ranked_latest_effective_ids(
    model: Any,
    *partition_columns: Any,
    predicates: list[Any],
    order_by: tuple[Any, ...],
):
    return (
        select(
            model.id.label("id"),
            func.row_number()
            .over(
                partition_by=partition_columns,
                order_by=order_by,
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


class ReferenceDataRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def resolve_benchmark_assignment(self, portfolio_id: str, as_of_date: date):
        stmt = (
            select(PortfolioBenchmarkAssignment)
            .where(
                PortfolioBenchmarkAssignment.portfolio_id == portfolio_id,
                _effective_filter(
                    PortfolioBenchmarkAssignment.effective_from,
                    PortfolioBenchmarkAssignment.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                PortfolioBenchmarkAssignment.effective_from.desc(),
                PortfolioBenchmarkAssignment.assignment_recorded_at.desc(),
                PortfolioBenchmarkAssignment.assignment_version.desc(),
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def resolve_model_portfolio_definition(
        self,
        model_portfolio_id: str,
        as_of_date: date,
    ):
        stmt = (
            select(ModelPortfolioDefinition)
            .where(
                ModelPortfolioDefinition.model_portfolio_id == model_portfolio_id,
                ModelPortfolioDefinition.approval_status == "approved",
                _effective_filter(
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
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_model_portfolio_targets(
        self,
        model_portfolio_id: str,
        model_portfolio_version: str,
        as_of_date: date,
        *,
        include_inactive_targets: bool = False,
    ) -> list[ModelPortfolioTarget]:
        predicates = [
            ModelPortfolioTarget.model_portfolio_id == model_portfolio_id,
            ModelPortfolioTarget.model_portfolio_version == model_portfolio_version,
            _effective_filter(
                ModelPortfolioTarget.effective_from,
                ModelPortfolioTarget.effective_to,
                as_of_date,
            ),
        ]
        if not include_inactive_targets:
            predicates.append(ModelPortfolioTarget.target_status == "active")

        ranked = _ranked_model_portfolio_target_ids(*predicates)
        stmt = (
            select(ModelPortfolioTarget)
            .join(ranked, ModelPortfolioTarget.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(ModelPortfolioTarget.instrument_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_model_portfolio_affected_mandates(
        self,
        model_portfolio_id: str,
        as_of_date: date,
        *,
        booking_center_code: str | None = None,
        include_inactive_mandates: bool = False,
    ) -> list[PortfolioMandateBinding]:
        predicates = [
            PortfolioMandateBinding.model_portfolio_id == model_portfolio_id,
            PortfolioMandateBinding.mandate_type == "discretionary",
            _effective_filter(
                PortfolioMandateBinding.effective_from,
                PortfolioMandateBinding.effective_to,
                as_of_date,
            ),
        ]
        if booking_center_code:
            predicates.append(PortfolioMandateBinding.booking_center_code == booking_center_code)
        if not include_inactive_mandates:
            predicates.append(PortfolioMandateBinding.discretionary_authority_status == "active")

        ranked = _ranked_portfolio_mandate_binding_ids(*predicates)
        stmt = (
            select(PortfolioMandateBinding)
            .join(ranked, PortfolioMandateBinding.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                PortfolioMandateBinding.portfolio_id.asc(),
                PortfolioMandateBinding.mandate_id.asc(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_dpm_portfolio_universe_candidates(
        self,
        *,
        as_of_date: date,
        booking_center_code: str | None = None,
        model_portfolio_ids: list[str] | None = None,
        include_inactive_mandates: bool = False,
        after_sort_key: tuple[str, str] | None = None,
        limit: int | None = None,
    ) -> list[PortfolioMandateBinding]:
        predicates = [
            PortfolioMandateBinding.mandate_type == "discretionary",
            _effective_filter(
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
            predicates.append(PortfolioMandateBinding.discretionary_authority_status == "active")

        ranked = _ranked_portfolio_mandate_binding_ids(*predicates)
        stmt = (
            select(PortfolioMandateBinding)
            .join(ranked, PortfolioMandateBinding.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                PortfolioMandateBinding.portfolio_id.asc(),
                PortfolioMandateBinding.mandate_id.asc(),
            )
        )
        if after_sort_key is not None:
            stmt = stmt.where(
                tuple_(
                    PortfolioMandateBinding.portfolio_id,
                    PortfolioMandateBinding.mandate_id,
                )
                > after_sort_key
            )
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def resolve_discretionary_mandate_binding(
        self,
        portfolio_id: str,
        as_of_date: date,
        *,
        mandate_id: str | None = None,
        booking_center_code: str | None = None,
    ):
        stmt = (
            select(PortfolioMandateBinding)
            .where(
                PortfolioMandateBinding.portfolio_id == portfolio_id,
                PortfolioMandateBinding.mandate_type == "discretionary",
                _effective_filter(
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
            stmt = stmt.where(PortfolioMandateBinding.mandate_id == mandate_id)
        if booking_center_code:
            stmt = stmt.where(PortfolioMandateBinding.booking_center_code == booking_center_code)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_client_restriction_profiles(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None = None,
        include_inactive_restrictions: bool = False,
    ) -> list[ClientRestrictionProfile]:
        predicates = [
            ClientRestrictionProfile.portfolio_id == portfolio_id,
            ClientRestrictionProfile.client_id == client_id,
            _effective_filter(
                ClientRestrictionProfile.effective_from,
                ClientRestrictionProfile.effective_to,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    ClientRestrictionProfile.mandate_id.is_(None),
                    ClientRestrictionProfile.mandate_id == mandate_id,
                )
            )
        if not include_inactive_restrictions:
            predicates.append(ClientRestrictionProfile.restriction_status == "active")

        ranked = _ranked_latest_effective_ids(
            ClientRestrictionProfile,
            ClientRestrictionProfile.restriction_scope,
            ClientRestrictionProfile.restriction_code,
            predicates=predicates,
            order_by=(
                ClientRestrictionProfile.effective_from.desc(),
                ClientRestrictionProfile.observed_at.desc().nullslast(),
                ClientRestrictionProfile.restriction_version.desc(),
                ClientRestrictionProfile.updated_at.desc(),
                ClientRestrictionProfile.created_at.desc(),
                ClientRestrictionProfile.id.desc(),
            ),
        )
        stmt = (
            select(ClientRestrictionProfile)
            .join(ranked, ClientRestrictionProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                ClientRestrictionProfile.restriction_scope.asc(),
                ClientRestrictionProfile.restriction_code.asc(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_sustainability_preference_profiles(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None = None,
        include_inactive_preferences: bool = False,
    ) -> list[SustainabilityPreferenceProfile]:
        predicates = [
            SustainabilityPreferenceProfile.portfolio_id == portfolio_id,
            SustainabilityPreferenceProfile.client_id == client_id,
            _effective_filter(
                SustainabilityPreferenceProfile.effective_from,
                SustainabilityPreferenceProfile.effective_to,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    SustainabilityPreferenceProfile.mandate_id.is_(None),
                    SustainabilityPreferenceProfile.mandate_id == mandate_id,
                )
            )
        if not include_inactive_preferences:
            predicates.append(SustainabilityPreferenceProfile.preference_status == "active")

        ranked = _ranked_latest_effective_ids(
            SustainabilityPreferenceProfile,
            SustainabilityPreferenceProfile.preference_framework,
            SustainabilityPreferenceProfile.preference_code,
            predicates=predicates,
            order_by=(
                SustainabilityPreferenceProfile.effective_from.desc(),
                SustainabilityPreferenceProfile.observed_at.desc().nullslast(),
                SustainabilityPreferenceProfile.preference_version.desc(),
                SustainabilityPreferenceProfile.updated_at.desc(),
                SustainabilityPreferenceProfile.created_at.desc(),
                SustainabilityPreferenceProfile.id.desc(),
            ),
        )
        stmt = (
            select(SustainabilityPreferenceProfile)
            .join(ranked, SustainabilityPreferenceProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                SustainabilityPreferenceProfile.preference_framework.asc(),
                SustainabilityPreferenceProfile.preference_code.asc(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_client_tax_profiles(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None = None,
        include_inactive_profiles: bool = False,
    ) -> list[ClientTaxProfile]:
        predicates = [
            ClientTaxProfile.portfolio_id == portfolio_id,
            ClientTaxProfile.client_id == client_id,
            _effective_filter(
                ClientTaxProfile.effective_from,
                ClientTaxProfile.effective_to,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    ClientTaxProfile.mandate_id.is_(None),
                    ClientTaxProfile.mandate_id == mandate_id,
                )
            )
        if not include_inactive_profiles:
            predicates.append(ClientTaxProfile.profile_status == "active")

        ranked = _ranked_latest_effective_ids(
            ClientTaxProfile,
            ClientTaxProfile.tax_profile_id,
            predicates=predicates,
            order_by=(
                ClientTaxProfile.effective_from.desc(),
                ClientTaxProfile.observed_at.desc().nullslast(),
                ClientTaxProfile.profile_version.desc(),
                ClientTaxProfile.updated_at.desc(),
                ClientTaxProfile.created_at.desc(),
                ClientTaxProfile.id.desc(),
            ),
        )
        stmt = (
            select(ClientTaxProfile)
            .join(ranked, ClientTaxProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(ClientTaxProfile.tax_profile_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_client_tax_rule_sets(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None = None,
        include_inactive_rules: bool = False,
    ) -> list[ClientTaxRuleSet]:
        predicates = [
            ClientTaxRuleSet.portfolio_id == portfolio_id,
            ClientTaxRuleSet.client_id == client_id,
            _effective_filter(
                ClientTaxRuleSet.effective_from,
                ClientTaxRuleSet.effective_to,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    ClientTaxRuleSet.mandate_id.is_(None),
                    ClientTaxRuleSet.mandate_id == mandate_id,
                )
            )
        if not include_inactive_rules:
            predicates.append(ClientTaxRuleSet.rule_status == "active")

        ranked = _ranked_latest_effective_ids(
            ClientTaxRuleSet,
            ClientTaxRuleSet.rule_set_id,
            ClientTaxRuleSet.jurisdiction_code,
            ClientTaxRuleSet.rule_code,
            predicates=predicates,
            order_by=(
                ClientTaxRuleSet.effective_from.desc(),
                ClientTaxRuleSet.observed_at.desc().nullslast(),
                ClientTaxRuleSet.rule_version.desc(),
                ClientTaxRuleSet.updated_at.desc(),
                ClientTaxRuleSet.created_at.desc(),
                ClientTaxRuleSet.id.desc(),
            ),
        )
        stmt = (
            select(ClientTaxRuleSet)
            .join(ranked, ClientTaxRuleSet.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                ClientTaxRuleSet.rule_set_id.asc(),
                ClientTaxRuleSet.jurisdiction_code.asc(),
                ClientTaxRuleSet.rule_code.asc(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_client_income_needs_schedules(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None = None,
        include_inactive_schedules: bool = False,
    ) -> list[ClientIncomeNeedsSchedule]:
        predicates = [
            ClientIncomeNeedsSchedule.portfolio_id == portfolio_id,
            ClientIncomeNeedsSchedule.client_id == client_id,
            _effective_filter(
                ClientIncomeNeedsSchedule.start_date,
                ClientIncomeNeedsSchedule.end_date,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    ClientIncomeNeedsSchedule.mandate_id.is_(None),
                    ClientIncomeNeedsSchedule.mandate_id == mandate_id,
                )
            )
        if not include_inactive_schedules:
            predicates.append(ClientIncomeNeedsSchedule.need_status == "active")

        ranked = _ranked_latest_effective_ids(
            ClientIncomeNeedsSchedule,
            ClientIncomeNeedsSchedule.schedule_id,
            predicates=predicates,
            order_by=(
                ClientIncomeNeedsSchedule.start_date.desc(),
                ClientIncomeNeedsSchedule.observed_at.desc().nullslast(),
                ClientIncomeNeedsSchedule.updated_at.desc(),
                ClientIncomeNeedsSchedule.created_at.desc(),
                ClientIncomeNeedsSchedule.id.desc(),
            ),
        )
        stmt = (
            select(ClientIncomeNeedsSchedule)
            .join(ranked, ClientIncomeNeedsSchedule.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(ClientIncomeNeedsSchedule.schedule_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_liquidity_reserve_requirements(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None = None,
        include_inactive_requirements: bool = False,
    ) -> list[LiquidityReserveRequirement]:
        predicates = [
            LiquidityReserveRequirement.portfolio_id == portfolio_id,
            LiquidityReserveRequirement.client_id == client_id,
            _effective_filter(
                LiquidityReserveRequirement.effective_from,
                LiquidityReserveRequirement.effective_to,
                as_of_date,
            ),
        ]
        if mandate_id:
            predicates.append(
                or_(
                    LiquidityReserveRequirement.mandate_id.is_(None),
                    LiquidityReserveRequirement.mandate_id == mandate_id,
                )
            )
        if not include_inactive_requirements:
            predicates.append(LiquidityReserveRequirement.reserve_status == "active")

        ranked = _ranked_latest_effective_ids(
            LiquidityReserveRequirement,
            LiquidityReserveRequirement.reserve_requirement_id,
            predicates=predicates,
            order_by=(
                LiquidityReserveRequirement.effective_from.desc(),
                LiquidityReserveRequirement.observed_at.desc().nullslast(),
                LiquidityReserveRequirement.requirement_version.desc(),
                LiquidityReserveRequirement.updated_at.desc(),
                LiquidityReserveRequirement.created_at.desc(),
                LiquidityReserveRequirement.id.desc(),
            ),
        )
        stmt = (
            select(LiquidityReserveRequirement)
            .join(ranked, LiquidityReserveRequirement.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(LiquidityReserveRequirement.reserve_requirement_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_planned_withdrawal_schedules(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        horizon_days: int,
        mandate_id: str | None = None,
        include_inactive_withdrawals: bool = False,
    ) -> list[PlannedWithdrawalSchedule]:
        window_end = as_of_date + timedelta(days=horizon_days)
        predicates = [
            PlannedWithdrawalSchedule.portfolio_id == portfolio_id,
            PlannedWithdrawalSchedule.client_id == client_id,
            PlannedWithdrawalSchedule.scheduled_date >= as_of_date,
            PlannedWithdrawalSchedule.scheduled_date <= window_end,
        ]
        if mandate_id:
            predicates.append(
                or_(
                    PlannedWithdrawalSchedule.mandate_id.is_(None),
                    PlannedWithdrawalSchedule.mandate_id == mandate_id,
                )
            )
        if not include_inactive_withdrawals:
            predicates.append(PlannedWithdrawalSchedule.withdrawal_status == "active")

        ranked = _ranked_latest_effective_ids(
            PlannedWithdrawalSchedule,
            PlannedWithdrawalSchedule.withdrawal_schedule_id,
            PlannedWithdrawalSchedule.scheduled_date,
            predicates=predicates,
            order_by=(
                PlannedWithdrawalSchedule.observed_at.desc().nullslast(),
                PlannedWithdrawalSchedule.updated_at.desc(),
                PlannedWithdrawalSchedule.created_at.desc(),
                PlannedWithdrawalSchedule.id.desc(),
            ),
        )
        stmt = (
            select(PlannedWithdrawalSchedule)
            .join(ranked, PlannedWithdrawalSchedule.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                PlannedWithdrawalSchedule.scheduled_date.asc(),
                PlannedWithdrawalSchedule.withdrawal_schedule_id.asc(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_instrument_eligibility_profiles(
        self,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[InstrumentEligibilityProfile]:
        normalized_security_ids = [
            normalized
            for security_id in security_ids
            if (normalized := normalize_security_id(security_id))
        ]
        if not normalized_security_ids:
            return []
        security_id_expr = func.trim(InstrumentEligibilityProfile.security_id)
        predicates = (
            security_id_expr.in_(normalized_security_ids),
            _effective_filter(
                InstrumentEligibilityProfile.effective_from,
                InstrumentEligibilityProfile.effective_to,
                as_of_date,
            ),
        )
        ranked = _ranked_instrument_eligibility_ids(security_id_expr, *predicates)
        stmt = (
            select(InstrumentEligibilityProfile)
            .join(ranked, InstrumentEligibilityProfile.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(security_id_expr.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_benchmark_definition(self, benchmark_id: str, as_of_date: date):
        stmt = (
            select(BenchmarkDefinition)
            .where(
                BenchmarkDefinition.benchmark_id == benchmark_id,
                _effective_filter(
                    BenchmarkDefinition.effective_from,
                    BenchmarkDefinition.effective_to,
                    as_of_date,
                ),
            )
            .order_by(BenchmarkDefinition.effective_from.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_benchmark_definitions_overlapping_window(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> list[BenchmarkDefinition]:
        stmt = (
            select(BenchmarkDefinition)
            .where(
                BenchmarkDefinition.benchmark_id == benchmark_id,
                BenchmarkDefinition.effective_from <= end_date,
                or_(
                    BenchmarkDefinition.effective_to.is_(None),
                    BenchmarkDefinition.effective_to >= start_date,
                ),
            )
            .order_by(BenchmarkDefinition.effective_from.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_definitions(
        self,
        as_of_date: date,
        benchmark_type: str | None = None,
        benchmark_currency: str | None = None,
        benchmark_status: str | None = None,
    ) -> list[BenchmarkDefinition]:
        predicates = [
            _effective_filter(
                BenchmarkDefinition.effective_from,
                BenchmarkDefinition.effective_to,
                as_of_date,
            )
        ]
        if benchmark_type:
            predicates.append(BenchmarkDefinition.benchmark_type == benchmark_type)
        if benchmark_currency:
            predicates.append(
                BenchmarkDefinition.benchmark_currency
                == normalize_currency_code(benchmark_currency)
            )
        if benchmark_status:
            predicates.append(
                BenchmarkDefinition.benchmark_status
                == _normalize_reference_status(benchmark_status)
            )

        ranked = _ranked_latest_effective_ids(
            BenchmarkDefinition,
            BenchmarkDefinition.benchmark_id,
            predicates=predicates,
            order_by=(
                BenchmarkDefinition.effective_from.desc(),
                BenchmarkDefinition.source_timestamp.desc().nullslast(),
                BenchmarkDefinition.updated_at.desc(),
                BenchmarkDefinition.created_at.desc(),
                BenchmarkDefinition.id.desc(),
            ),
        )
        stmt = (
            select(BenchmarkDefinition)
            .join(ranked, BenchmarkDefinition.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkDefinition.benchmark_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_definitions(
        self,
        as_of_date: date,
        index_ids: list[str] | None = None,
        index_currency: str | None = None,
        index_type: str | None = None,
        index_status: str | None = None,
    ) -> list[IndexDefinition]:
        predicates = [
            _effective_filter(
                IndexDefinition.effective_from,
                IndexDefinition.effective_to,
                as_of_date,
            )
        ]
        if index_ids:
            predicates.append(IndexDefinition.index_id.in_(index_ids))
        if index_currency:
            predicates.append(
                IndexDefinition.index_currency == normalize_currency_code(index_currency)
            )
        if index_type:
            predicates.append(IndexDefinition.index_type == index_type)
        if index_status:
            predicates.append(
                IndexDefinition.index_status == _normalize_reference_status(index_status)
            )

        ranked = _ranked_latest_effective_ids(
            IndexDefinition,
            IndexDefinition.index_id,
            predicates=predicates,
            order_by=(
                IndexDefinition.effective_from.desc(),
                IndexDefinition.source_timestamp.desc().nullslast(),
                IndexDefinition.updated_at.desc(),
                IndexDefinition.created_at.desc(),
                IndexDefinition.id.desc(),
            ),
        )
        stmt = (
            select(IndexDefinition)
            .join(ranked, IndexDefinition.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexDefinition.index_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components(
        self,
        benchmark_id: str,
        as_of_date: date,
    ) -> list[BenchmarkCompositionSeries]:
        predicates = [
            BenchmarkCompositionSeries.benchmark_id == benchmark_id,
            _effective_filter(
                BenchmarkCompositionSeries.composition_effective_from,
                BenchmarkCompositionSeries.composition_effective_to,
                as_of_date,
            ),
        ]
        ranked = _ranked_latest_effective_ids(
            BenchmarkCompositionSeries,
            BenchmarkCompositionSeries.benchmark_id,
            BenchmarkCompositionSeries.index_id,
            predicates=predicates,
            order_by=(
                BenchmarkCompositionSeries.composition_effective_from.desc(),
                BenchmarkCompositionSeries.source_timestamp.desc().nullslast(),
                BenchmarkCompositionSeries.updated_at.desc(),
                BenchmarkCompositionSeries.created_at.desc(),
                BenchmarkCompositionSeries.id.desc(),
            ),
        )
        stmt = (
            select(BenchmarkCompositionSeries)
            .join(ranked, BenchmarkCompositionSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkCompositionSeries.index_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components_overlapping_window(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        index_ids: list[str] | None = None,
    ) -> list[BenchmarkCompositionSeries]:
        if index_ids is not None and not index_ids:
            return []

        stmt = select(BenchmarkCompositionSeries).where(
            BenchmarkCompositionSeries.benchmark_id == benchmark_id,
            BenchmarkCompositionSeries.composition_effective_from <= end_date,
            or_(
                BenchmarkCompositionSeries.composition_effective_to.is_(None),
                BenchmarkCompositionSeries.composition_effective_to >= start_date,
            ),
        )
        if index_ids:
            stmt = stmt.where(BenchmarkCompositionSeries.index_id.in_(index_ids))
        stmt = stmt.order_by(
            BenchmarkCompositionSeries.composition_effective_from.asc(),
            BenchmarkCompositionSeries.index_id.asc(),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_component_index_ids_overlapping_window(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        *,
        after_index_id: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        stmt = (
            select(BenchmarkCompositionSeries.index_id)
            .distinct()
            .where(
                BenchmarkCompositionSeries.benchmark_id == benchmark_id,
                BenchmarkCompositionSeries.composition_effective_from <= end_date,
                or_(
                    BenchmarkCompositionSeries.composition_effective_to.is_(None),
                    BenchmarkCompositionSeries.composition_effective_to >= start_date,
                ),
            )
        )
        if after_index_id:
            stmt = stmt.where(BenchmarkCompositionSeries.index_id > after_index_id)
        stmt = stmt.order_by(BenchmarkCompositionSeries.index_id.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components_for_benchmarks(
        self,
        benchmark_ids: list[str],
        as_of_date: date,
    ) -> dict[str, list[BenchmarkCompositionSeries]]:
        if not benchmark_ids:
            return {}

        predicates = [
            BenchmarkCompositionSeries.benchmark_id.in_(benchmark_ids),
            _effective_filter(
                BenchmarkCompositionSeries.composition_effective_from,
                BenchmarkCompositionSeries.composition_effective_to,
                as_of_date,
            ),
        ]
        ranked = _ranked_latest_effective_ids(
            BenchmarkCompositionSeries,
            BenchmarkCompositionSeries.benchmark_id,
            BenchmarkCompositionSeries.index_id,
            predicates=predicates,
            order_by=(
                BenchmarkCompositionSeries.composition_effective_from.desc(),
                BenchmarkCompositionSeries.source_timestamp.desc().nullslast(),
                BenchmarkCompositionSeries.updated_at.desc(),
                BenchmarkCompositionSeries.created_at.desc(),
                BenchmarkCompositionSeries.id.desc(),
            ),
        )
        stmt = (
            select(BenchmarkCompositionSeries)
            .join(ranked, BenchmarkCompositionSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                BenchmarkCompositionSeries.benchmark_id.asc(),
                BenchmarkCompositionSeries.index_id.asc(),
            )
        )
        rows = list((await self._db.execute(stmt)).scalars().all())
        grouped: dict[str, list[BenchmarkCompositionSeries]] = defaultdict(list)
        for row in rows:
            grouped[row.benchmark_id].append(row)
        return dict(grouped)

    async def list_index_price_points(
        self,
        index_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> list[IndexPriceSeries]:
        if not index_ids:
            return []
        predicates = (
            IndexPriceSeries.index_id.in_(index_ids),
            IndexPriceSeries.series_date >= start_date,
            IndexPriceSeries.series_date <= end_date,
        )
        ranked = _canonical_series_ranked_subquery(
            IndexPriceSeries,
            IndexPriceSeries.index_id,
            IndexPriceSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexPriceSeries)
            .join(ranked, IndexPriceSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexPriceSeries.index_id.asc(), IndexPriceSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_return_points(
        self,
        index_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> list[IndexReturnSeries]:
        if not index_ids:
            return []
        predicates = (
            IndexReturnSeries.index_id.in_(index_ids),
            IndexReturnSeries.series_date >= start_date,
            IndexReturnSeries.series_date <= end_date,
        )
        ranked = _canonical_series_ranked_subquery(
            IndexReturnSeries,
            IndexReturnSeries.index_id,
            IndexReturnSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexReturnSeries)
            .join(ranked, IndexReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexReturnSeries.index_id.asc(), IndexReturnSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_return_points(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> list[BenchmarkReturnSeries]:
        predicates = (
            BenchmarkReturnSeries.benchmark_id == benchmark_id,
            BenchmarkReturnSeries.series_date >= start_date,
            BenchmarkReturnSeries.series_date <= end_date,
        )
        ranked = _canonical_series_ranked_subquery(
            BenchmarkReturnSeries,
            BenchmarkReturnSeries.benchmark_id,
            BenchmarkReturnSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(BenchmarkReturnSeries)
            .join(ranked, BenchmarkReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkReturnSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_price_series(
        self, index_id: str, start_date: date, end_date: date
    ) -> list[IndexPriceSeries]:
        predicates = (
            IndexPriceSeries.index_id == index_id,
            IndexPriceSeries.series_date >= start_date,
            IndexPriceSeries.series_date <= end_date,
        )
        ranked = _canonical_series_ranked_subquery(
            IndexPriceSeries,
            IndexPriceSeries.index_id,
            IndexPriceSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexPriceSeries)
            .join(ranked, IndexPriceSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexPriceSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_return_series(
        self, index_id: str, start_date: date, end_date: date
    ) -> list[IndexReturnSeries]:
        predicates = (
            IndexReturnSeries.index_id == index_id,
            IndexReturnSeries.series_date >= start_date,
            IndexReturnSeries.series_date <= end_date,
        )
        ranked = _canonical_series_ranked_subquery(
            IndexReturnSeries,
            IndexReturnSeries.index_id,
            IndexReturnSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexReturnSeries)
            .join(ranked, IndexReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexReturnSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_risk_free_series(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> list[RiskFreeSeries]:
        predicates = (
            RiskFreeSeries.series_currency == normalize_currency_code(currency),
            RiskFreeSeries.series_date >= start_date,
            RiskFreeSeries.series_date <= end_date,
        )
        ranked = _canonical_series_ranked_subquery(
            RiskFreeSeries,
            RiskFreeSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(RiskFreeSeries)
            .join(ranked, RiskFreeSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(RiskFreeSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> list[ClassificationTaxonomy]:
        stmt = select(ClassificationTaxonomy).where(
            _effective_filter(
                ClassificationTaxonomy.effective_from,
                ClassificationTaxonomy.effective_to,
                as_of_date,
            )
        )
        if taxonomy_scope:
            stmt = stmt.where(ClassificationTaxonomy.taxonomy_scope == taxonomy_scope)
        result = await self._db.execute(
            stmt.order_by(
                ClassificationTaxonomy.taxonomy_scope.asc(),
                ClassificationTaxonomy.dimension_name.asc(),
                ClassificationTaxonomy.dimension_value.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        components = await self.list_benchmark_components_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )
        index_ids = sorted({row.index_id for row in components})
        price_points = await self.list_index_price_points(
            index_ids=index_ids,
            start_date=start_date,
            end_date=end_date,
        )
        benchmark_returns = await self.list_benchmark_return_points(
            benchmark_id,
            start_date,
            end_date,
        )
        observed_dates = observed_benchmark_coverage_dates(
            components=components,
            price_points=price_points,
            benchmark_returns=benchmark_returns,
            start_date=start_date,
            end_date=end_date,
        )
        total_points = len(price_points) + len(benchmark_returns)
        observed_start = min(observed_dates) if observed_dates else None
        observed_end = max(observed_dates) if observed_dates else None
        coverage_rows = price_points + benchmark_returns
        return {
            "total_points": total_points,
            "observed_start_date": observed_start,
            "observed_end_date": observed_end,
            "observed_dates": observed_dates,
            "quality_status_counts": quality_status_counts(coverage_rows),
            "latest_evidence_timestamp": latest_reference_evidence_timestamp(coverage_rows),
        }

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        points = await self.list_risk_free_series(currency, start_date, end_date)
        all_dates = [row.series_date for row in points]
        observed_start = min(all_dates) if all_dates else None
        observed_end = max(all_dates) if all_dates else None
        return {
            "total_points": len(points),
            "observed_start_date": observed_start,
            "observed_end_date": observed_end,
            "quality_status_counts": quality_status_counts(points),
            "observed_dates": all_dates,
            "latest_evidence_timestamp": latest_reference_evidence_timestamp(points),
        }

    async def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        from_currency_expr = currency_code_sql_expr(FxRate.from_currency)
        to_currency_expr = currency_code_sql_expr(FxRate.to_currency)
        stmt = (
            select(FxRate)
            .where(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date >= start_date,
                FxRate.rate_date <= end_date,
            )
            .order_by(FxRate.rate_date.asc())
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        rates: dict[date, Decimal] = {}
        for row in rows:
            rate = decimal_or_none(row.rate)
            if rate is not None:
                rates[row.rate_date] = rate
        return rates

    async def list_latest_market_prices(
        self,
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[MarketPrice]:
        normalized_security_ids = [
            normalized
            for security_id in security_ids
            if (normalized := normalize_security_id(security_id))
        ]
        normalized_security_ids = list(dict.fromkeys(normalized_security_ids))
        if not normalized_security_ids:
            return []
        security_id_expr = func.trim(MarketPrice.security_id)

        latest_price_dates = (
            select(
                security_id_expr.label("security_id"),
                func.max(MarketPrice.price_date).label("latest_price_date"),
            )
            .where(
                security_id_expr.in_(normalized_security_ids),
                MarketPrice.price_date <= as_of_date,
            )
            .group_by(security_id_expr)
            .subquery()
        )
        stmt = (
            select(MarketPrice)
            .join(
                latest_price_dates,
                and_(
                    security_id_expr == latest_price_dates.c.security_id,
                    MarketPrice.price_date == latest_price_dates.c.latest_price_date,
                ),
            )
            .order_by(security_id_expr.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_latest_fx_rates(
        self,
        *,
        currency_pairs: list[tuple[str, str]],
        as_of_date: date,
    ) -> list[FxRate]:
        if not currency_pairs:
            return []

        normalized_pairs = normalized_currency_pairs(currency_pairs)
        if not normalized_pairs:
            return []
        stmt = latest_fx_rates_stmt(
            normalized_pairs=normalized_pairs,
            as_of_date=as_of_date,
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
