"""SQLAlchemy adapter for effective portfolio benchmark assignment evidence."""

from datetime import date
from typing import Any

from portfolio_common.database_models import PortfolioBenchmarkAssignment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.benchmark_assignment import BenchmarkAssignmentEvidence
from .effective_profile_queries import effective_on


class SqlAlchemyBenchmarkAssignmentReader:
    """Select the latest effective assignment with deterministic tie-breaking."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self, *, portfolio_id: str, as_of_date: date
    ) -> BenchmarkAssignmentEvidence | None:
        statement = (
            select(PortfolioBenchmarkAssignment)
            .where(
                PortfolioBenchmarkAssignment.portfolio_id == portfolio_id,
                effective_on(
                    PortfolioBenchmarkAssignment.effective_from,
                    PortfolioBenchmarkAssignment.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                PortfolioBenchmarkAssignment.effective_from.desc(),
                PortfolioBenchmarkAssignment.assignment_recorded_at.desc(),
                PortfolioBenchmarkAssignment.assignment_version.desc(),
                PortfolioBenchmarkAssignment.id.desc(),
            )
            .limit(1)
        )
        row = (await self._session.execute(statement)).scalars().first()
        return _to_evidence(row) if row is not None else None


def _to_evidence(row: Any) -> BenchmarkAssignmentEvidence:
    return BenchmarkAssignmentEvidence(
        portfolio_id=row.portfolio_id,
        benchmark_id=row.benchmark_id,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        assignment_source=row.assignment_source,
        assignment_status=row.assignment_status,
        policy_pack_id=row.policy_pack_id,
        source_system=row.source_system,
        assignment_recorded_at=row.assignment_recorded_at,
        assignment_version=int(row.assignment_version),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
