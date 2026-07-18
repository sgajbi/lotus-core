"""Persistence-adapter tests for portfolio-manager book membership."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.portfolio_party_roles import PortfolioPartyRoleType

from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_manager_book_sources,
)


@pytest.mark.asyncio
async def test_reader_prefers_effective_portfolio_manager_role_assignments() -> None:
    row = SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_GLOBAL_BAL_001",
        booking_center_code="Singapore",
        portfolio_type="DISCRETIONARY",
        status="ACTIVE",
        open_date=date(2025, 3, 31),
        close_date=None,
        base_currency="SGD",
        created_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )
    assignment = SimpleNamespace(
        role_type="discretionary_portfolio_manager",
        source_system="relationship_master",
        source_record_id="coverage-PB_SG_GLOBAL_BAL_001-PM-001",
        observed_at=datetime(2026, 5, 3, 9, 30, tzinfo=UTC),
    )
    authoritative_result = MagicMock()
    authoritative_result.all.return_value = [(row, assignment)]
    legacy_result = MagicMock()
    legacy_result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[authoritative_result, legacy_result])

    records = await portfolio_manager_book_sources.SqlAlchemyPortfolioManagerBookReader(
        session
    ).list_members(
        portfolio_manager_id="PM_SG_DPM_001",
        as_of_date=date(2026, 5, 3),
        booking_center_code="Singapore",
        portfolio_types=("DISCRETIONARY",),
        include_inactive=False,
    )

    assert records[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert records[0].membership_source == "party_role_assignment"
    assert records[0].role_type is PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER
    assert records[0].source_record_id == "coverage-PB_SG_GLOBAL_BAL_001-PM-001"
    authoritative_sql = str(session.execute.await_args_list[0].args[0])
    assert "row_number() OVER" in authoritative_sql
    assert "portfolio_party_role_assignments.party_id" in authoritative_sql
    assert "portfolio_party_role_assignments.role_type IN" in authoritative_sql
    assert "portfolio_party_role_assignments.quality_status" in authoritative_sql
    assert "portfolios.booking_center_code" in authoritative_sql
    legacy_sql = str(session.execute.await_args_list[1].args[0])
    assert "portfolios.advisor_id" in legacy_sql
    assert "NOT (EXISTS" in legacy_sql


@pytest.mark.asyncio
async def test_reader_retains_advisor_projection_only_for_unmigrated_portfolios() -> None:
    row = SimpleNamespace(
        portfolio_id="PB_LEGACY_001",
        client_id="CIF_LEGACY_001",
        booking_center_code="Singapore",
        portfolio_type="DISCRETIONARY",
        status="ACTIVE",
        open_date=date(2025, 3, 31),
        close_date=None,
        base_currency="SGD",
        created_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )
    authoritative_result = MagicMock()
    authoritative_result.all.return_value = []
    legacy_result = MagicMock()
    legacy_result.scalars.return_value.all.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[authoritative_result, legacy_result])

    records = await portfolio_manager_book_sources.SqlAlchemyPortfolioManagerBookReader(
        session
    ).list_members(
        portfolio_manager_id="LEGACY_ADVISOR_001",
        as_of_date=date(2026, 5, 3),
        booking_center_code=None,
        portfolio_types=(),
        include_inactive=True,
    )

    assert records[0].membership_source == "legacy_advisor_projection"
    assert records[0].role_type is None
    assert records[0].source_record_id is None
