"""SQLAlchemy adapter for effective portfolio party-role assignments."""

from datetime import date
from typing import Any

from portfolio_common.database_models import PortfolioPartyRoleAssignment
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.portfolio_party_roles import PortfolioPartyRoleRecord


class SqlAlchemyPortfolioPartyRoleReader:
    """Resolve latest source versions before applying effective-date and quality filters."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_effective_assignments(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        party_id: str | None,
        role_types: tuple[PortfolioPartyRoleType, ...],
        role_scopes: tuple[PortfolioPartyRoleScope, ...],
        include_non_accepted: bool,
    ) -> list[PortfolioPartyRoleRecord]:
        ranked = (
            select(
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
            )
            .cte("ranked_portfolio_party_roles")
        )
        statement = (
            select(PortfolioPartyRoleAssignment)
            .join(
                ranked,
                PortfolioPartyRoleAssignment.id == ranked.c.assignment_id,
            )
            .where(
                ranked.c.source_rank == 1,
                PortfolioPartyRoleAssignment.portfolio_id == portfolio_id,
                PortfolioPartyRoleAssignment.effective_from <= as_of_date,
                or_(
                    PortfolioPartyRoleAssignment.effective_to.is_(None),
                    PortfolioPartyRoleAssignment.effective_to >= as_of_date,
                ),
            )
        )
        if party_id:
            statement = statement.where(PortfolioPartyRoleAssignment.party_id == party_id)
        if role_types:
            statement = statement.where(PortfolioPartyRoleAssignment.role_type.in_(role_types))
        if role_scopes:
            statement = statement.where(PortfolioPartyRoleAssignment.role_scope.in_(role_scopes))
        if not include_non_accepted:
            statement = statement.where(
                PortfolioPartyRoleAssignment.quality_status
                == PortfolioPartyRoleQualityStatus.ACCEPTED
            )
        statement = statement.order_by(
            PortfolioPartyRoleAssignment.role_type.asc(),
            PortfolioPartyRoleAssignment.role_scope.asc(),
            PortfolioPartyRoleAssignment.party_id.asc(),
            PortfolioPartyRoleAssignment.source_system.asc(),
            PortfolioPartyRoleAssignment.source_record_id.asc(),
        )
        result = await self._session.execute(statement)
        return [_record(row) for row in result.scalars().all()]


def _record(row: Any) -> PortfolioPartyRoleRecord:
    return PortfolioPartyRoleRecord(
        portfolio_id=row.portfolio_id,
        party_id=row.party_id,
        role_type=PortfolioPartyRoleType(row.role_type),
        role_scope=PortfolioPartyRoleScope(row.role_scope),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        assignment_version=row.assignment_version,
        source_system=row.source_system,
        source_record_id=row.source_record_id,
        observed_at=row.observed_at,
        quality_status=PortfolioPartyRoleQualityStatus(row.quality_status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
