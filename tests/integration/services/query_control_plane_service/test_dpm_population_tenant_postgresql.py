"""PostgreSQL tenant-isolation proof for DPM population source selections."""

from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import (
    ModelPortfolioDefinition,
    Portfolio,
    PortfolioMandateBinding,
    PortfolioPartyRoleAssignment,
)
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from portfolio_common.domain.tenant import TenantId
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    dpm_portfolio_population_sources,
    portfolio_manager_book_sources,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]

TENANT_A = TenantId("tenant-population-a")
TENANT_B = TenantId("tenant-population-b")
AS_OF_DATE = date(2026, 5, 3)
MODEL_ID = "MODEL_SHARED_POPULATION"
PORTFOLIO_A = "PB_POPULATION_TENANT_A"
PORTFOLIO_B = "PB_POPULATION_TENANT_B"
PORTFOLIO_MANAGER = "PM_SHARED_POPULATION"


def _portfolio(*, tenant_id: TenantId, portfolio_id: str, advisor_id: str | None) -> Portfolio:
    return Portfolio(
        tenant_id=tenant_id.value,
        portfolio_id=portfolio_id,
        base_currency="SGD",
        open_date=date(2020, 1, 1),
        risk_exposure="BALANCED",
        investment_time_horizon="LONG_TERM",
        portfolio_type="DISCRETIONARY",
        booking_center_code="Singapore",
        client_id=f"CLIENT_{portfolio_id}",
        is_leverage_allowed=False,
        advisor_id=advisor_id,
        status="ACTIVE",
    )


def _mandate(*, portfolio_id: str, mandate_id: str) -> PortfolioMandateBinding:
    return PortfolioMandateBinding(
        portfolio_id=portfolio_id,
        mandate_id=mandate_id,
        client_id=f"CLIENT_{portfolio_id}",
        mandate_type="discretionary",
        discretionary_authority_status="active",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        model_portfolio_id=MODEL_ID,
        risk_profile="balanced",
        investment_horizon="long_term",
        rebalance_frequency="monthly",
        rebalance_bands={},
        effective_from=date(2026, 1, 1),
        binding_version=1,
        source_system="tenant-postgresql-proof",
        source_record_id=f"mandate:{mandate_id}",
        observed_at=datetime(2026, 5, 2, tzinfo=UTC),
        quality_status="accepted",
    )


async def test_population_selectors_never_cross_the_admitted_portfolio_tenant(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Shared PM/model identifiers return only rows rooted in the admitted tenant."""

    async_db_session.add_all(
        [
            _portfolio(
                tenant_id=TENANT_A,
                portfolio_id=PORTFOLIO_A,
                advisor_id=None,
            ),
            _portfolio(
                tenant_id=TENANT_B,
                portfolio_id=PORTFOLIO_B,
                advisor_id=PORTFOLIO_MANAGER,
            ),
            ModelPortfolioDefinition(
                model_portfolio_id=MODEL_ID,
                model_portfolio_version="2026.05",
                display_name="Shared population model",
                base_currency="SGD",
                risk_profile="balanced",
                mandate_type="discretionary",
                approval_status="approved",
                approved_at=datetime(2026, 5, 1, tzinfo=UTC),
                effective_from=date(2026, 5, 1),
                source_system="tenant-postgresql-proof",
                source_record_id="model:shared-population",
                observed_at=datetime(2026, 5, 1, tzinfo=UTC),
                quality_status="accepted",
            ),
            _mandate(portfolio_id=PORTFOLIO_A, mandate_id="MANDATE_POPULATION_A"),
            _mandate(portfolio_id=PORTFOLIO_B, mandate_id="MANDATE_POPULATION_B"),
            PortfolioPartyRoleAssignment(
                portfolio_id=PORTFOLIO_A,
                party_id=PORTFOLIO_MANAGER,
                role_type=PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,
                role_scope=PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT,
                effective_from=date(2026, 1, 1),
                assignment_version=1,
                source_system="tenant-postgresql-proof",
                source_record_id="pm-role:population-a",
                observed_at=datetime(2026, 5, 2, tzinfo=UTC),
                quality_status=PortfolioPartyRoleQualityStatus.ACCEPTED,
            ),
        ]
    )
    await async_db_session.commit()

    population_reader = dpm_portfolio_population_sources.SqlAlchemyDpmPortfolioPopulationReader(
        async_db_session
    )
    book_reader = portfolio_manager_book_sources.SqlAlchemyPortfolioManagerBookReader(
        async_db_session
    )

    tenant_a_cohort = await population_reader.list_affected_mandates(
        tenant_id=TENANT_A,
        model_portfolio_id=MODEL_ID,
        as_of_date=AS_OF_DATE,
        booking_center_code=None,
        include_inactive_mandates=False,
    )
    tenant_b_universe = await population_reader.list_universe_candidates(
        tenant_id=TENANT_B,
        as_of_date=AS_OF_DATE,
        booking_center_code=None,
        model_portfolio_ids=(MODEL_ID,),
        include_inactive_mandates=False,
        after_sort_key=None,
        limit=10,
    )
    tenant_a_book = await book_reader.list_members(
        tenant_id=TENANT_A,
        portfolio_manager_id=PORTFOLIO_MANAGER,
        as_of_date=AS_OF_DATE,
        booking_center_code=None,
        portfolio_types=("DISCRETIONARY",),
        include_inactive=False,
    )
    tenant_b_book = await book_reader.list_members(
        tenant_id=TENANT_B,
        portfolio_manager_id=PORTFOLIO_MANAGER,
        as_of_date=AS_OF_DATE,
        booking_center_code=None,
        portfolio_types=("DISCRETIONARY",),
        include_inactive=False,
    )

    assert [row.portfolio_id for row in tenant_a_cohort] == [PORTFOLIO_A]
    assert [row.portfolio_id for row in tenant_b_universe] == [PORTFOLIO_B]
    assert [row.portfolio_id for row in tenant_a_book] == [PORTFOLIO_A]
    assert [row.portfolio_id for row in tenant_b_book] == [PORTFOLIO_B]
    assert tenant_a_book[0].membership_source == "party_role_assignment"
    assert tenant_b_book[0].membership_source == "legacy_advisor_projection"
