"""SQLAlchemy adapter for client income, reserve, and withdrawal evidence."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import (
    ClientIncomeNeedsSchedule,
    LiquidityReserveRequirement,
    PlannedWithdrawalSchedule,
)
from portfolio_common.source_lifecycle_predicates import (
    CLIENT_INCOME_NEEDS_ACTIVE,
    LIQUIDITY_RESERVE_ACTIVE,
    PLANNED_WITHDRAWAL_ACTIVE,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.client_liquidity_evidence import (
    ClientIncomeNeedSourceRecord,
    LiquidityReserveRequirementSourceRecord,
    PlannedWithdrawalSourceRecord,
)
from .effective_profile_queries import effective_on, ranked_latest_ids


class SqlAlchemyClientLiquidityEvidenceReader:
    """Select client liquidity evidence with deterministic precedence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_income_needs(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_schedules: bool,
    ) -> list[ClientIncomeNeedSourceRecord]:
        predicates = [
            ClientIncomeNeedsSchedule.portfolio_id == portfolio_id,
            ClientIncomeNeedsSchedule.client_id == client_id,
            effective_on(
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
            predicates.append(
                CLIENT_INCOME_NEEDS_ACTIVE.sqlalchemy_filter(ClientIncomeNeedsSchedule.need_status)
            )
        ranked = ranked_latest_ids(
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
        result = await self._session.execute(
            select(ClientIncomeNeedsSchedule)
            .join(ranked, ClientIncomeNeedsSchedule.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(ClientIncomeNeedsSchedule.schedule_id.asc())
        )
        return [_income_record(row) for row in result.scalars().all()]

    async def list_reserve_requirements(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_requirements: bool,
    ) -> list[LiquidityReserveRequirementSourceRecord]:
        predicates = [
            LiquidityReserveRequirement.portfolio_id == portfolio_id,
            LiquidityReserveRequirement.client_id == client_id,
            effective_on(
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
            predicates.append(
                LIQUIDITY_RESERVE_ACTIVE.sqlalchemy_filter(
                    LiquidityReserveRequirement.reserve_status
                )
            )
        ranked = ranked_latest_ids(
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
        result = await self._session.execute(
            select(LiquidityReserveRequirement)
            .join(ranked, LiquidityReserveRequirement.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(LiquidityReserveRequirement.reserve_requirement_id.asc())
        )
        return [_reserve_record(row) for row in result.scalars().all()]

    async def list_planned_withdrawals(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        horizon_days: int,
        mandate_id: str | None,
        include_inactive_withdrawals: bool,
    ) -> list[PlannedWithdrawalSourceRecord]:
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
            predicates.append(
                PLANNED_WITHDRAWAL_ACTIVE.sqlalchemy_filter(
                    PlannedWithdrawalSchedule.withdrawal_status
                )
            )
        ranked = ranked_latest_ids(
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
        result = await self._session.execute(
            select(PlannedWithdrawalSchedule)
            .join(ranked, PlannedWithdrawalSchedule.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(
                PlannedWithdrawalSchedule.scheduled_date.asc(),
                PlannedWithdrawalSchedule.withdrawal_schedule_id.asc(),
            )
        )
        return [_withdrawal_record(row) for row in result.scalars().all()]


def _income_record(row: Any) -> ClientIncomeNeedSourceRecord:
    return ClientIncomeNeedSourceRecord(
        schedule_id=row.schedule_id,
        need_type=row.need_type,
        need_status=row.need_status,
        amount=Decimal(str(row.amount)),
        currency=row.currency,
        frequency=row.frequency,
        start_date=row.start_date,
        end_date=row.end_date,
        priority=int(row.priority),
        funding_policy=row.funding_policy,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _reserve_record(row: Any) -> LiquidityReserveRequirementSourceRecord:
    return LiquidityReserveRequirementSourceRecord(
        reserve_requirement_id=row.reserve_requirement_id,
        reserve_type=row.reserve_type,
        reserve_status=row.reserve_status,
        required_amount=Decimal(str(row.required_amount)),
        currency=row.currency,
        horizon_days=int(row.horizon_days),
        priority=int(row.priority),
        policy_source=row.policy_source,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        requirement_version=int(row.requirement_version),
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _withdrawal_record(row: Any) -> PlannedWithdrawalSourceRecord:
    return PlannedWithdrawalSourceRecord(
        withdrawal_schedule_id=row.withdrawal_schedule_id,
        withdrawal_type=row.withdrawal_type,
        withdrawal_status=row.withdrawal_status,
        amount=Decimal(str(row.amount)),
        currency=row.currency,
        scheduled_date=row.scheduled_date,
        recurrence_frequency=row.recurrence_frequency,
        purpose_code=row.purpose_code,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
