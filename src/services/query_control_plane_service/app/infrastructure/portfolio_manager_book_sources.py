"""SQLAlchemy source adapter for portfolio-manager book membership."""

from datetime import date
from typing import Any

from portfolio_common.database_models import Portfolio, PortfolioPartyRoleAssignment
from portfolio_common.domain.portfolio_party_roles import (
    PORTFOLIO_MANAGER_ROLE_TYPES,
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.portfolio_manager_book import PortfolioManagerBookRecord


class SqlAlchemyPortfolioManagerBookReader:
    """Select deterministic effective memberships from the portfolio master."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_members(
        self,
        *,
        portfolio_manager_id: str,
        as_of_date: date,
        booking_center_code: str | None,
        portfolio_types: tuple[str, ...],
        include_inactive: bool,
    ) -> list[PortfolioManagerBookRecord]:
        ranked = select(
            PortfolioPartyRoleAssignment.id.label("assignment_id"),
            func.row_number()
            .over(
                partition_by=(
                    PortfolioPartyRoleAssignment.source_system,
                    PortfolioPartyRoleAssignment.source_record_id,
                ),
                order_by=(
                    PortfolioPartyRoleAssignment.assignment_version.desc(),
                    PortfolioPartyRoleAssignment.observed_at.desc(),
                    PortfolioPartyRoleAssignment.updated_at.desc(),
                    PortfolioPartyRoleAssignment.id.desc(),
                ),
            )
            .label("source_rank"),
        ).cte("ranked_pm_role_assignments")
        authoritative = (
            select(Portfolio, PortfolioPartyRoleAssignment)
            .join(
                PortfolioPartyRoleAssignment,
                PortfolioPartyRoleAssignment.portfolio_id == Portfolio.portfolio_id,
            )
            .join(ranked, PortfolioPartyRoleAssignment.id == ranked.c.assignment_id)
            .where(
                ranked.c.source_rank == 1,
                PortfolioPartyRoleAssignment.party_id == portfolio_manager_id,
                PortfolioPartyRoleAssignment.role_type.in_(PORTFOLIO_MANAGER_ROLE_TYPES),
                PortfolioPartyRoleAssignment.role_scope
                == PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT,
                PortfolioPartyRoleAssignment.quality_status
                == PortfolioPartyRoleQualityStatus.ACCEPTED,
                PortfolioPartyRoleAssignment.effective_from <= as_of_date,
                or_(
                    PortfolioPartyRoleAssignment.effective_to.is_(None),
                    PortfolioPartyRoleAssignment.effective_to >= as_of_date,
                ),
                *_portfolio_filters(
                    as_of_date=as_of_date,
                    booking_center_code=booking_center_code,
                    portfolio_types=portfolio_types,
                    include_inactive=include_inactive,
                ),
            )
            .order_by(
                Portfolio.portfolio_id.asc(),
                PortfolioPartyRoleAssignment.role_type.asc(),
                PortfolioPartyRoleAssignment.source_system.asc(),
                PortfolioPartyRoleAssignment.source_record_id.asc(),
            )
        )
        authoritative_result = await self._session.execute(authoritative)
        members = {
            portfolio.portfolio_id: _portfolio_manager_book_record(portfolio, assignment)
            for portfolio, assignment in authoritative_result.all()
        }

        any_role_history = exists(
            select(1).where(PortfolioPartyRoleAssignment.portfolio_id == Portfolio.portfolio_id)
        )
        legacy = (
            select(Portfolio)
            .where(
                Portfolio.advisor_id == portfolio_manager_id,
                ~any_role_history,
                *_portfolio_filters(
                    as_of_date=as_of_date,
                    booking_center_code=booking_center_code,
                    portfolio_types=portfolio_types,
                    include_inactive=include_inactive,
                ),
            )
            .order_by(Portfolio.portfolio_id.asc())
        )
        legacy_result = await self._session.execute(legacy)
        for portfolio in legacy_result.scalars().all():
            members.setdefault(portfolio.portfolio_id, _portfolio_manager_book_record(portfolio))
        return [members[portfolio_id] for portfolio_id in sorted(members)]


def _portfolio_filters(
    *,
    as_of_date: date,
    booking_center_code: str | None,
    portfolio_types: tuple[str, ...],
    include_inactive: bool,
) -> list[Any]:
    filters: list[Any] = []
    if booking_center_code:
        filters.append(Portfolio.booking_center_code == booking_center_code)
    if portfolio_types:
        filters.append(Portfolio.portfolio_type.in_(_storage_case_variants(portfolio_types)))
    if not include_inactive:
        filters.extend(
            (
                Portfolio.open_date <= as_of_date,
                or_(Portfolio.close_date.is_(None), Portfolio.close_date >= as_of_date),
                Portfolio.status.in_(_storage_case_variants(("ACTIVE",))),
            )
        )
    return filters


def _storage_case_variants(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return known persisted enum casings without wrapping indexed columns."""

    variants: list[str] = []
    for value in values:
        normalized = value.strip().upper()
        if normalized:
            variants.extend((normalized, normalized.lower(), normalized.title()))
    return tuple(dict.fromkeys(variants))


def _portfolio_manager_book_record(
    row: Any, assignment: Any | None = None
) -> PortfolioManagerBookRecord:
    return PortfolioManagerBookRecord(
        portfolio_id=row.portfolio_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        portfolio_type=row.portfolio_type,
        status=row.status,
        open_date=row.open_date,
        close_date=row.close_date,
        base_currency=row.base_currency,
        created_at=row.created_at,
        updated_at=row.updated_at,
        membership_source=(
            "party_role_assignment" if assignment is not None else "legacy_advisor_projection"
        ),
        role_type=(
            PortfolioPartyRoleType(assignment.role_type) if assignment is not None else None
        ),
        source_system=(assignment.source_system if assignment is not None else None),
        source_record_id=(assignment.source_record_id if assignment is not None else None),
        observed_at=(assignment.observed_at if assignment is not None else None),
    )
