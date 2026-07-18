from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_party_role_sources,
)


@pytest.mark.asyncio
async def test_party_role_reader_ranks_source_versions_before_effective_quality_filters() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalars = Mock()
    scalars.all.return_value = []
    result = Mock()
    result.scalars.return_value = scalars
    session.execute.return_value = result

    records = await portfolio_party_role_sources.SqlAlchemyPortfolioPartyRoleReader(
        session
    ).list_effective_assignments(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=date(2026, 7, 18),
        party_id="PARTY_PM_SG_001",
        role_types=(PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,),
        role_scopes=(PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT,),
        include_non_accepted=False,
    )

    assert records == []
    statement = session.execute.await_args.args[0]
    sql = " ".join(str(statement).split()).lower()
    assert "row_number() over (partition by" in sql
    assert "source_system" in sql and "source_record_id" in sql
    assert "assignment_version desc" in sql
    assert "ranked_portfolio_party_roles.source_rank =" in sql
    assert "effective_from <=" in sql and "effective_to >=" in sql
    assert "quality_status =" in sql
    assert "party_id =" in sql and "role_type in" in sql and "role_scope in" in sql


@pytest.mark.asyncio
async def test_party_role_reader_can_include_latest_nonaccepted_observations() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalars = Mock()
    scalars.all.return_value = []
    result = Mock()
    result.scalars.return_value = scalars
    session.execute.return_value = result

    await portfolio_party_role_sources.SqlAlchemyPortfolioPartyRoleReader(
        session
    ).list_effective_assignments(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=date(2026, 7, 18),
        party_id=None,
        role_types=(),
        role_scopes=(),
        include_non_accepted=True,
    )

    sql = " ".join(str(session.execute.await_args.args[0]).split()).lower()
    where_clause = sql.split("order by", maxsplit=1)[0]
    assert "quality_status =" not in where_clause
