"""PostgreSQL tenant-isolation proof for DPM population source selections."""

from datetime import UTC, date, datetime

import httpx
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
from portfolio_common.page_tokens import PageTokenCodec
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.DTOs.reference_data_discretionary_mandate_dto import (
    DiscretionaryMandateBindingRecord,
)
from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.query_control_plane_service.app.application.dpm_portfolio_population import (
    DpmPortfolioPopulationService,
)
from src.services.query_control_plane_service.app.contracts.dpm_portfolio_population import (
    CioModelChangeAffectedCohortRequest,
    CioModelChangeAffectedCohortResponse,
    DpmPortfolioUniverseCandidateRequest,
    DpmPortfolioUniverseCandidateResponse,
)
from src.services.query_control_plane_service.app.dependencies import (
    get_dpm_portfolio_population_service,
)
from src.services.query_control_plane_service.app.infrastructure import (
    dpm_portfolio_population_sources,
    dpm_reference_data_sources,
    portfolio_manager_book_sources,
)
from src.services.query_control_plane_service.app.main import app

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]

TENANT_A = TenantId("tenant-population-a")
TENANT_B = TenantId("tenant-population-b")
AS_OF_DATE = date(2026, 5, 3)
MODEL_ID = "MODEL_SHARED_POPULATION"
PORTFOLIO_A = "PB_POPULATION_TENANT_A"
PORTFOLIO_B = "PB_POPULATION_TENANT_B"
PORTFOLIO_MANAGER = "PM_SHARED_POPULATION"
VERSIONED_PORTFOLIO = "PB_VERSIONED_MANDATE_POPULATION"
VERSIONED_MANDATE = "MANDATE_VERSIONED_POPULATION"


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 12, 2, tzinfo=UTC)


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


def _model(model_portfolio_id: str) -> ModelPortfolioDefinition:
    return ModelPortfolioDefinition(
        model_portfolio_id=model_portfolio_id,
        model_portfolio_version="2026.01",
        display_name=f"Version selection proof {model_portfolio_id}",
        base_currency="SGD",
        risk_profile="balanced",
        mandate_type="discretionary",
        approval_status="approved",
        approved_at=datetime(2025, 12, 31, tzinfo=UTC),
        effective_from=date(2026, 1, 1),
        source_system="mandate-version-selection-proof",
        source_record_id=f"model:{model_portfolio_id}",
        observed_at=datetime(2025, 12, 31, tzinfo=UTC),
        quality_status="accepted",
    )


def _versioned_mandate(
    *,
    binding_version: int,
    authority_status: str,
    model_portfolio_id: str,
    observed_at: datetime,
    booking_center_code: str = "Singapore",
    effective_from: date = date(2026, 1, 1),
) -> dict[str, object]:
    return DiscretionaryMandateBindingRecord(
        portfolio_id=VERSIONED_PORTFOLIO,
        mandate_id=VERSIONED_MANDATE,
        client_id="CLIENT_VERSIONED_MANDATE",
        discretionary_authority_status=authority_status,
        booking_center_code=booking_center_code,
        jurisdiction_code="SG",
        model_portfolio_id=model_portfolio_id,
        risk_profile="balanced",
        investment_horizon="long_term",
        rebalance_frequency="monthly",
        rebalance_bands={},
        effective_from=effective_from,
        binding_version=binding_version,
        source_system="mandate-version-selection-proof",
        source_record_id=f"mandate-version:{binding_version}",
        observed_at=observed_at,
        quality_status="accepted",
    ).model_dump()


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


async def test_population_filters_only_the_current_effective_mandate_version(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Suspended and reassigned successors prevent obsolete cohort membership."""

    async_db_session.add_all(
        [
            _portfolio(
                tenant_id=TENANT_A,
                portfolio_id=VERSIONED_PORTFOLIO,
                advisor_id=None,
            ),
            *[_model(model_id) for model_id in ("MODEL_A", "MODEL_B", "MODEL_C", "MODEL_D")],
        ]
    )
    await async_db_session.commit()
    ingestion = ReferenceDataIngestionService(async_db_session)
    population_reader = dpm_portfolio_population_sources.SqlAlchemyDpmPortfolioPopulationReader(
        async_db_session
    )
    binding_reader = dpm_reference_data_sources.SqlAlchemyDpmReferenceDataReader(async_db_session)
    service = DpmPortfolioPopulationService(
        reader=population_reader,
        page_tokens=PageTokenCodec(secret="mandate-version-selection-proof"),
        clock=_Clock(),
    )
    monkeypatch.setitem(
        app.dependency_overrides, get_dpm_portfolio_population_service, lambda: service
    )

    async def post(path: str, payload: dict[str, object]) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(path, json=payload, headers={"X-Tenant-Id": TENANT_A.value})

    async def affected(
        model_id: str,
        *,
        as_of_date: date = date(2026, 4, 1),
        booking_center_code: str | None = None,
        include_inactive: bool = False,
    ):
        response = await post(
            f"/integration/model-portfolios/{model_id}/affected-mandates",
            {
                "as_of_date": as_of_date.isoformat(),
                "booking_center_code": booking_center_code,
                "include_inactive_mandates": include_inactive,
            },
        )
        if response.status_code == 404:
            assert response.json()["metadata"]["reason"] == "empty_result"
            return []
        assert response.status_code == 200, response.text
        return CioModelChangeAffectedCohortResponse.model_validate(
            response.json()
        ).affected_mandates

    async def universe(
        model_id: str,
        *,
        as_of_date: date = date(2026, 4, 1),
        booking_center_code: str | None = None,
        include_inactive: bool = False,
    ):
        response = await post(
            "/integration/dpm/portfolio-universe/candidates",
            {
                "as_of_date": as_of_date.isoformat(),
                "booking_center_code": booking_center_code,
                "model_portfolio_ids": [model_id],
                "include_inactive_mandates": include_inactive,
            },
        )
        if response.status_code == 404:
            assert response.json()["metadata"]["reason"] == "empty_result"
            return []
        assert response.status_code == 200, response.text
        return DpmPortfolioUniverseCandidateResponse.model_validate(response.json()).candidates

    await ingestion.upsert_discretionary_mandate_bindings(
        [
            _versioned_mandate(
                binding_version=1,
                authority_status="active",
                model_portfolio_id="MODEL_A",
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
    )
    assert [row.binding_version for row in await affected("MODEL_A")] == [1]
    assert [row.binding_version for row in await universe("MODEL_A")] == [1]

    await ingestion.upsert_discretionary_mandate_bindings(
        [
            _versioned_mandate(
                binding_version=2,
                authority_status="suspended",
                model_portfolio_id="MODEL_A",
                observed_at=datetime(2026, 2, 1, tzinfo=UTC),
            )
        ]
    )
    assert await affected("MODEL_A") == []
    assert await universe("MODEL_A") == []
    assert [row.binding_version for row in await affected("MODEL_A", include_inactive=True)] == [2]
    assert [row.binding_version for row in await universe("MODEL_A", include_inactive=True)] == [2]

    await ingestion.upsert_discretionary_mandate_bindings(
        [
            _versioned_mandate(
                binding_version=3,
                authority_status="active",
                model_portfolio_id="MODEL_B",
                observed_at=datetime(2026, 3, 1, tzinfo=UTC),
            )
        ]
    )
    assert await affected("MODEL_A", include_inactive=True) == []
    assert await universe("MODEL_A", include_inactive=True) == []
    assert [row.binding_version for row in await affected("MODEL_B")] == [3]
    assert [row.binding_version for row in await universe("MODEL_B")] == [3]

    model_a_cohort = await service.resolve_cio_model_change_cohort(
        tenant_id=TENANT_A,
        model_portfolio_id="MODEL_A",
        request=CioModelChangeAffectedCohortRequest(as_of_date=date(2026, 4, 1)),
    )
    model_b_cohort = await service.resolve_cio_model_change_cohort(
        tenant_id=TENANT_A,
        model_portfolio_id="MODEL_B",
        request=CioModelChangeAffectedCohortRequest(as_of_date=date(2026, 4, 1)),
    )
    model_a_universe = await service.resolve_universe_candidates(
        tenant_id=TENANT_A,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 4, 1), model_portfolio_ids=["MODEL_A"]
        ),
    )
    model_b_universe = await service.resolve_universe_candidates(
        tenant_id=TENANT_A,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 4, 1), model_portfolio_ids=["MODEL_B"]
        ),
    )
    assert model_a_cohort is not None
    assert model_a_cohort.affected_mandates == []
    assert model_a_cohort.supportability.state == "INCOMPLETE"
    assert model_b_cohort is not None
    assert [row.binding_version for row in model_b_cohort.affected_mandates] == [3]
    assert model_a_universe.candidates == []
    assert model_a_universe.supportability.state == "INCOMPLETE"
    assert [row.binding_version for row in model_b_universe.candidates] == [3]

    binding = await binding_reader.resolve_discretionary_mandate_binding(
        portfolio_id=VERSIONED_PORTFOLIO,
        as_of_date=date(2026, 4, 1),
        mandate_id=VERSIONED_MANDATE,
        booking_center_code=None,
    )
    assert binding is not None
    assert binding.binding_version == 3
    assert binding.model_portfolio_id == "MODEL_B"

    await ingestion.upsert_discretionary_mandate_bindings(
        [
            _versioned_mandate(
                binding_version=4,
                authority_status="active",
                model_portfolio_id="MODEL_B",
                booking_center_code="Hong Kong",
                observed_at=datetime(2026, 4, 2, tzinfo=UTC),
            )
        ]
    )
    assert await affected("MODEL_B", booking_center_code="Singapore") == []
    assert [
        row.binding_version for row in await universe("MODEL_B", booking_center_code="Hong Kong")
    ] == [4]
    assert (
        await binding_reader.resolve_discretionary_mandate_binding(
            portfolio_id=VERSIONED_PORTFOLIO,
            as_of_date=date(2026, 4, 3),
            mandate_id=VERSIONED_MANDATE,
            booking_center_code="Singapore",
        )
        is None
    )

    await ingestion.upsert_discretionary_mandate_bindings(
        [
            _versioned_mandate(
                binding_version=5,
                authority_status="active",
                model_portfolio_id="MODEL_A",
                observed_at=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            _versioned_mandate(
                binding_version=6,
                authority_status="active",
                model_portfolio_id="MODEL_B",
                effective_from=date(2026, 12, 1),
                observed_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
        ]
    )
    assert [row.binding_version for row in await affected("MODEL_A")] == [5]
    assert await affected("MODEL_B") == []
    assert [
        row.binding_version for row in await affected("MODEL_B", as_of_date=date(2026, 12, 1))
    ] == [6]

    tie_observed_at = datetime(2026, 7, 1, tzinfo=UTC)
    await ingestion.upsert_discretionary_mandate_bindings(
        [
            _versioned_mandate(
                binding_version=7,
                authority_status="active",
                model_portfolio_id="MODEL_C",
                effective_from=date(2026, 12, 1),
                observed_at=tie_observed_at,
            ),
            _versioned_mandate(
                binding_version=8,
                authority_status="active",
                model_portfolio_id="MODEL_D",
                effective_from=date(2026, 12, 1),
                observed_at=tie_observed_at,
            ),
        ]
    )
    assert await universe("MODEL_C", as_of_date=date(2026, 12, 2)) == []
    assert [
        row.binding_version for row in await universe("MODEL_D", as_of_date=date(2026, 12, 2))
    ] == [8]

    independent = _versioned_mandate(
        binding_version=1,
        authority_status="active",
        model_portfolio_id="MODEL_A",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    independent.update(mandate_id="MANDATE_INDEPENDENT", source_record_id="independent:1")
    async_db_session.add(_portfolio(tenant_id=TENANT_B, portfolio_id=PORTFOLIO_B, advisor_id=None))
    await async_db_session.commit()
    foreign = dict(independent)
    foreign.update(portfolio_id=PORTFOLIO_B, source_record_id="foreign:1")
    await ingestion.upsert_discretionary_mandate_bindings([independent, foreign])
    assert [row.mandate_id for row in await affected("MODEL_A")] == [
        "MANDATE_INDEPENDENT",
        VERSIONED_MANDATE,
    ]
    assert [row.mandate_id for row in await universe("MODEL_A", as_of_date=date(2026, 12, 2))] == [
        "MANDATE_INDEPENDENT"
    ]

    first_page = await post(
        "/integration/dpm/portfolio-universe/candidates",
        {"as_of_date": "2026-12-02", "page": {"page_size": 1}},
    )
    assert first_page.status_code == 200, first_page.text
    first = first_page.json()
    assert len(first["candidates"]) == 1
    assert first["candidates"][0]["mandate_id"] == "MANDATE_INDEPENDENT"
    next_page = await post(
        "/integration/dpm/portfolio-universe/candidates",
        {
            "as_of_date": "2026-12-02",
            "page": {"page_size": 1, "page_token": first["page"]["next_page_token"]},
        },
    )
    assert next_page.status_code == 200, next_page.text
    second = next_page.json()
    assert [(row["mandate_id"], row["binding_version"]) for row in second["candidates"]] == [
        (VERSIONED_MANDATE, 8)
    ]
    assert second["page"]["next_page_token"] is None
    assert first["page"]["request_scope_fingerprint"] == second["page"]["request_scope_fingerprint"]
