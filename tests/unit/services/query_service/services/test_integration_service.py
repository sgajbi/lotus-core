from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.reconciliation_quality import BLOCKED, COMPLETE, PARTIAL, STALE, UNRECONCILED
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.reference_integration_dto import (
    CioModelChangeAffectedCohortRequest,
    ClientIncomeNeedsScheduleRequest,
    ClientRestrictionProfileRequest,
    ClientTaxProfileRequest,
    ClientTaxRuleSetRequest,
    DiscretionaryMandateBindingRequest,
    DpmSourceReadinessRequest,
    ExternalCurrencyExposureRequest,
    ExternalHedgeExecutionReadinessRequest,
    ExternalHedgePolicyRequest,
    InstrumentEligibilityBulkRequest,
    LiquidityReserveRequirementRequest,
    MarketDataCoverageRequest,
    ModelPortfolioTargetRequest,
    PlannedWithdrawalScheduleRequest,
    PortfolioManagerBookMembershipRequest,
    PortfolioTaxLotWindowRequest,
    SustainabilityPreferenceProfileRequest,
    TransactionCostCurveRequest,
)
from src.services.query_service.app.services.integration_service import IntegrationService


def make_service() -> IntegrationService:
    return IntegrationService(AsyncMock(spec=AsyncSession))


def transaction_cost_row(
    *,
    transaction_id: str,
    security_id: str,
    transaction_type: str = "BUY",
    currency: str = "USD",
    gross_transaction_amount: Decimal | None = Decimal("10000.00"),
    trade_fee: Decimal | None = Decimal("10.00"),
    costs: list[SimpleNamespace] | None = None,
    transaction_date: datetime = datetime(2026, 4, 1, 10, tzinfo=UTC),
) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        transaction_id=transaction_id,
        security_id=security_id,
        transaction_type=transaction_type,
        currency=currency,
        gross_transaction_amount=gross_transaction_amount,
        trade_fee=trade_fee,
        transaction_date=transaction_date,
        updated_at=transaction_date,
        costs=costs if costs is not None else [],
    )


def model_portfolio_target_request(as_of_date: date) -> ModelPortfolioTargetRequest:
    return ModelPortfolioTargetRequest(as_of_date=as_of_date)


def mandate_binding_request(as_of_date: date) -> DiscretionaryMandateBindingRequest:
    return DiscretionaryMandateBindingRequest(as_of_date=as_of_date)


def portfolio_manager_book_request(as_of_date: date) -> PortfolioManagerBookMembershipRequest:
    return PortfolioManagerBookMembershipRequest(
        as_of_date=as_of_date,
        booking_center_code="Singapore",
    )


def cio_model_change_request(as_of_date: date) -> CioModelChangeAffectedCohortRequest:
    return CioModelChangeAffectedCohortRequest(
        as_of_date=as_of_date,
        tenant_id="default",
        booking_center_code="Singapore",
    )


def profile_binding_row(as_of_date: date) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        effective_from=as_of_date,
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def instrument_eligibility_request(
    security_ids: list[str],
    as_of_date: date,
) -> InstrumentEligibilityBulkRequest:
    return InstrumentEligibilityBulkRequest(security_ids=security_ids, as_of_date=as_of_date)


def test_to_coverage_response_uses_exact_observed_dates_when_present() -> None:
    response = IntegrationService._to_coverage_response(  # pylint: disable=protected-access
        coverage={
            "total_points": 6,
            "observed_start_date": date(2026, 1, 1),
            "observed_end_date": date(2026, 1, 3),
            "observed_dates": [date(2026, 1, 1), date(2026, 1, 3)],
            "quality_status_counts": {"accepted": 6},
        },
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.missing_dates_count == 1
    assert response.missing_dates_sample == [date(2026, 1, 2)]
    assert response.request_fingerprint == "fp-coverage-test"
    assert response.data_quality_status == PARTIAL


@pytest.mark.asyncio
async def test_resolve_portfolio_manager_book_membership_returns_source_owned_members():
    service = make_service()
    service._portfolio_repository = AsyncMock()  # pylint: disable=protected-access
    service._portfolio_repository.list_portfolio_manager_book_members.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_GLOBAL_BAL_001",
            booking_center_code="Singapore",
            portfolio_type="DISCRETIONARY",
            status="ACTIVE",
            open_date=date(2025, 3, 31),
            close_date=None,
            base_currency="USD",
            created_at=datetime(2026, 5, 3, 1, 0, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 1, 5, tzinfo=UTC),
        )
    ]

    response = await service.resolve_portfolio_manager_book_membership(
        "PM_SG_DPM_001",
        portfolio_manager_book_request(date(2026, 5, 3)),
    )

    service._portfolio_repository.list_portfolio_manager_book_members.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=protected-access
        portfolio_manager_id="PM_SG_DPM_001",
        as_of_date=date(2026, 5, 3),
        booking_center_code="Singapore",
        portfolio_types=["DISCRETIONARY"],
        include_inactive=False,
    )
    assert response.product_name == "PortfolioManagerBookMembership"
    assert response.portfolio_manager_id == "PM_SG_DPM_001"
    assert response.supportability.state == "READY"
    assert response.supportability.returned_portfolio_count == 1
    assert response.members[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.members[0].source_record_id == "portfolio:PB_SG_GLOBAL_BAL_001"
    assert response.lineage["source_field"] == "advisor_id"
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("pm_book_membership:")


@pytest.mark.asyncio
async def test_resolve_portfolio_manager_book_membership_marks_empty_book_incomplete():
    service = make_service()
    service._portfolio_repository = AsyncMock()  # pylint: disable=protected-access
    service._portfolio_repository.list_portfolio_manager_book_members.return_value = []  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.resolve_portfolio_manager_book_membership(
        "PM_EMPTY",
        portfolio_manager_book_request(date(2026, 5, 3)),
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "PM_BOOK_MEMBERSHIP_EMPTY"
    assert response.members == []
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_resolve_cio_model_change_affected_cohort_returns_source_owned_mandates():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_model_portfolio_definition.return_value = SimpleNamespace(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        model_portfolio_version="2026.05",
        approval_status="approved",
        approved_at=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
        effective_from=date(2026, 5, 1),
        effective_to=None,
        source_system="cio_model_admin",
        source_record_id="model-def-2026-05",
        observed_at=datetime(2026, 5, 1, 8, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 8, 2, tzinfo=UTC),
    )
    service._reference_repository.list_model_portfolio_affected_mandates.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_000184",
            booking_center_code="Singapore",
            jurisdiction_code="SG",
            discretionary_authority_status="active",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            policy_pack_id="POLICY_DPM_SG_BALANCED_V1",
            risk_profile="balanced",
            effective_from=date(2026, 5, 1),
            effective_to=None,
            binding_version=3,
            source_record_id="mandate-binding-001",
            observed_at=datetime(2026, 5, 1, 8, 3, tzinfo=UTC),
            updated_at=datetime(2026, 5, 1, 8, 4, tzinfo=UTC),
        )
    ]

    response = await service.resolve_cio_model_change_affected_cohort(
        "MODEL_PB_SG_GLOBAL_BAL_DPM",
        cio_model_change_request(date(2026, 5, 3)),
    )

    service._reference_repository.resolve_model_portfolio_definition.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=protected-access
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        as_of_date=date(2026, 5, 3),
    )
    service._reference_repository.list_model_portfolio_affected_mandates.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=protected-access
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        as_of_date=date(2026, 5, 3),
        booking_center_code="Singapore",
        include_inactive_mandates=False,
    )
    assert response is not None
    assert response.product_name == "CioModelChangeAffectedCohort"
    assert response.model_change_event_id.startswith(
        "cio_model_change:MODEL_PB_SG_GLOBAL_BAL_DPM:2026.05:2026-05-03:"
    )
    assert response.supportability.state == "READY"
    assert response.supportability.returned_mandate_count == 1
    assert response.affected_mandates[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.affected_mandates[0].mandate_id == "MANDATE_PB_SG_GLOBAL_BAL_001"
    assert response.lineage["model_definition_source_record_id"] == "model-def-2026-05"
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("cio_model_change_cohort:")


@pytest.mark.asyncio
async def test_resolve_cio_model_change_affected_cohort_marks_empty_cohort_incomplete():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_model_portfolio_definition.return_value = SimpleNamespace(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        model_portfolio_id="MODEL_EMPTY",
        model_portfolio_version="2026.05",
        approval_status="approved",
        approved_at=None,
        effective_from=date(2026, 5, 1),
        effective_to=None,
        source_system=None,
        source_record_id=None,
        observed_at=None,
        updated_at=None,
    )
    service._reference_repository.list_model_portfolio_affected_mandates.return_value = []  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.resolve_cio_model_change_affected_cohort(
        "MODEL_EMPTY",
        cio_model_change_request(date(2026, 5, 3)),
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CIO_MODEL_CHANGE_COHORT_EMPTY"
    assert response.affected_mandates == []
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_resolve_cio_model_change_affected_cohort_returns_none_without_approved_model():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_model_portfolio_definition.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.resolve_cio_model_change_affected_cohort(
        "MODEL_MISSING",
        cio_model_change_request(date(2026, 5, 3)),
    )

    assert response is None
    service._reference_repository.list_model_portfolio_affected_mandates.assert_not_awaited()  # type: ignore[attr-defined] # pylint: disable=line-too-long


@pytest.mark.asyncio
async def test_client_restriction_profile_returns_ready_source_records():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_client_restriction_profiles.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            restriction_scope="asset_class",
            restriction_code="NO_PRIVATE_CREDIT_BUY",
            restriction_status="active",
            restriction_source="client_mandate",
            applies_to_buy=True,
            applies_to_sell=False,
            instrument_ids=[],
            asset_classes=["private_credit"],
            issuer_ids=[],
            country_codes=[],
            effective_from=date(2026, 1, 1),
            effective_to=None,
            restriction_version=1,
            source_record_id="client-restriction:1",
            observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        )
    ]

    response = await service.get_client_restriction_profile(
        "PB_SG_GLOBAL_BAL_001",
        ClientRestrictionProfileRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        ),
    )

    assert response is not None
    assert response.product_name == "ClientRestrictionProfile"
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert response.supportability.restriction_count == 1
    assert response.restrictions[0].restriction_code == "NO_PRIVATE_CREDIT_BUY"
    assert response.restrictions[0].asset_classes == ["private_credit"]
    assert response.lineage["source_table"] == (
        "client_restriction_profiles,portfolio_mandate_bindings"
    )
    service._reference_repository.list_client_restriction_profiles.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=as_of_date,
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_restrictions=False,
    )


@pytest.mark.asyncio
async def test_client_restriction_profile_marks_missing_profile_incomplete():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_client_restriction_profiles.return_value = []  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_client_restriction_profile(
        "PB_SG_GLOBAL_BAL_001",
        ClientRestrictionProfileRequest(as_of_date=as_of_date, tenant_id="default"),
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_RESTRICTION_PROFILE_EMPTY"
    assert response.supportability.missing_data_families == ["client_restrictions"]
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_sustainability_preference_profile_returns_ready_source_records():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_sustainability_preference_profiles.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            preference_framework="LOTUS_SUSTAINABILITY_V1",
            preference_code="MIN_SUSTAINABLE_ALLOCATION",
            preference_status="active",
            preference_source="client_mandate",
            minimum_allocation=Decimal("0.2000000000"),
            maximum_allocation=None,
            applies_to_asset_classes=["equity", "fixed_income"],
            exclusion_codes=["THERMAL_COAL"],
            positive_tilt_codes=["LOW_CARBON_TRANSITION"],
            effective_from=date(2026, 1, 1),
            effective_to=None,
            preference_version=1,
            source_record_id="sustainability:1",
            observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        )
    ]

    response = await service.get_sustainability_preference_profile(
        "PB_SG_GLOBAL_BAL_001",
        SustainabilityPreferenceProfileRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        ),
    )

    assert response is not None
    assert response.product_name == "SustainabilityPreferenceProfile"
    assert response.supportability.state == "READY"
    assert response.supportability.preference_count == 1
    assert response.preferences[0].minimum_allocation == Decimal("0.2000000000")
    assert response.preferences[0].exclusion_codes == ["THERMAL_COAL"]
    assert response.lineage["source_table"] == (
        "sustainability_preference_profiles,portfolio_mandate_bindings"
    )
    service._reference_repository.list_sustainability_preference_profiles.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=as_of_date,
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_preferences=False,
    )


@pytest.mark.asyncio
async def test_sustainability_preference_profile_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_sustainability_preference_profile(
        "PB_MISSING",
        SustainabilityPreferenceProfileRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    service._reference_repository.list_sustainability_preference_profiles.assert_not_awaited()  # type: ignore[attr-defined] # pylint: disable=line-too-long


@pytest.mark.asyncio
async def test_client_tax_profile_returns_ready_source_records():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_client_tax_profiles.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            tax_profile_id="TAX_PROFILE_SG_001",
            tax_residency_country="SG",
            booking_tax_jurisdiction="SG",
            tax_status="TAXABLE",
            profile_status="active",
            withholding_tax_rate=Decimal("0.1500000000"),
            capital_gains_tax_applicable=False,
            income_tax_applicable=True,
            treaty_codes=["US_SG_TREATY"],
            eligible_account_types=["DPM"],
            effective_from=date(2026, 1, 1),
            effective_to=None,
            profile_version=1,
            source_record_id="tax-profile:1",
            observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        )
    ]

    response = await service.get_client_tax_profile(
        "PB_SG_GLOBAL_BAL_001",
        ClientTaxProfileRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        ),
    )

    assert response is not None
    assert response.product_name == "ClientTaxProfile"
    assert response.supportability.state == "READY"
    assert response.supportability.profile_count == 1
    assert response.profiles[0].tax_profile_id == "TAX_PROFILE_SG_001"
    assert response.profiles[0].withholding_tax_rate == Decimal("0.1500000000")
    assert response.lineage["source_table"] == "client_tax_profiles,portfolio_mandate_bindings"
    service._reference_repository.list_client_tax_profiles.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=as_of_date,
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_profiles=False,
    )


@pytest.mark.asyncio
async def test_client_tax_profile_marks_missing_profile_incomplete():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_client_tax_profiles.return_value = []  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_client_tax_profile(
        "PB_SG_GLOBAL_BAL_001",
        ClientTaxProfileRequest(as_of_date=as_of_date, tenant_id="default"),
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_TAX_PROFILE_EMPTY"
    assert response.supportability.missing_data_families == ["client_tax_profile"]
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_client_tax_rule_set_returns_ready_source_records():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_client_tax_rule_sets.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            rule_set_id="TAX_RULES_SG_2026",
            tax_year=2026,
            jurisdiction_code="SG",
            rule_code="US_DIVIDEND_WITHHOLDING",
            rule_category="WITHHOLDING",
            rule_status="active",
            rule_source="bank_tax_reference",
            applies_to_asset_classes=[],
            applies_to_security_ids=[],
            applies_to_income_types=["DIVIDEND"],
            rate=Decimal("0.1500000000"),
            threshold_amount=None,
            threshold_currency=None,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            rule_version=1,
            source_record_id="tax-rule:1",
            observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        )
    ]

    response = await service.get_client_tax_rule_set(
        "PB_SG_GLOBAL_BAL_001",
        ClientTaxRuleSetRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        ),
    )

    assert response is not None
    assert response.product_name == "ClientTaxRuleSet"
    assert response.supportability.state == "READY"
    assert response.supportability.rule_count == 1
    assert response.rules[0].rule_code == "US_DIVIDEND_WITHHOLDING"
    assert response.rules[0].rate == Decimal("0.1500000000")
    assert response.lineage["source_table"] == "client_tax_rule_sets,portfolio_mandate_bindings"
    service._reference_repository.list_client_tax_rule_sets.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=as_of_date,
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_rules=False,
    )


@pytest.mark.asyncio
async def test_client_tax_rule_set_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_client_tax_rule_set(
        "PB_MISSING",
        ClientTaxRuleSetRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    service._reference_repository.list_client_tax_rule_sets.assert_not_awaited()  # type: ignore[attr-defined] # pylint: disable=line-too-long


@pytest.mark.asyncio
async def test_client_income_needs_schedule_returns_ready_source_records():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_client_income_needs_schedules.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            schedule_id="INCOME_NEED_MONTHLY_001",
            need_type="LIVING_EXPENSE",
            need_status="active",
            amount=Decimal("25000.0000"),
            currency="SGD",
            frequency="MONTHLY",
            start_date=date(2026, 4, 1),
            end_date=None,
            priority=1,
            funding_policy="POLICY_DPM_SG_BALANCED_V1",
            source_record_id="income-need:1",
            observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        )
    ]

    response = await service.get_client_income_needs_schedule(
        "PB_SG_GLOBAL_BAL_001",
        ClientIncomeNeedsScheduleRequest(as_of_date=as_of_date, tenant_id="default"),
    )

    assert response is not None
    assert response.product_name == "ClientIncomeNeedsSchedule"
    assert response.supportability.state == "READY"
    assert response.supportability.schedule_count == 1
    assert response.schedules[0].amount == Decimal("25000.0000")
    assert response.lineage["source_table"] == (
        "client_income_needs_schedules,portfolio_mandate_bindings"
    )
    service._reference_repository.list_client_income_needs_schedules.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=as_of_date,
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_schedules=False,
    )


@pytest.mark.asyncio
async def test_client_income_needs_schedule_marks_missing_schedule_incomplete():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_client_income_needs_schedules.return_value = []  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_client_income_needs_schedule(
        "PB_SG_GLOBAL_BAL_001",
        ClientIncomeNeedsScheduleRequest(as_of_date=as_of_date, tenant_id="default"),
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_INCOME_NEEDS_SCHEDULE_EMPTY"
    assert response.supportability.missing_data_families == ["client_income_needs_schedule"]
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_client_income_needs_schedule_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_client_income_needs_schedule(
        "PB_MISSING",
        ClientIncomeNeedsScheduleRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    service._reference_repository.list_client_income_needs_schedules.assert_not_awaited()  # type: ignore[attr-defined] # pylint: disable=line-too-long


@pytest.mark.asyncio
async def test_liquidity_reserve_requirement_returns_ready_source_records():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_liquidity_reserve_requirements.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            reserve_requirement_id="RESERVE_MIN_CASH_001",
            reserve_type="MIN_CASH_BUFFER",
            reserve_status="active",
            required_amount=Decimal("150000.0000"),
            currency="SGD",
            horizon_days=90,
            priority=1,
            policy_source="POLICY_DPM_SG_BALANCED_V1",
            effective_from=date(2026, 4, 1),
            effective_to=None,
            requirement_version=2,
            source_record_id="reserve:1",
            observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        )
    ]

    response = await service.get_liquidity_reserve_requirement(
        "PB_SG_GLOBAL_BAL_001",
        LiquidityReserveRequirementRequest(as_of_date=as_of_date, tenant_id="default"),
    )

    assert response is not None
    assert response.product_name == "LiquidityReserveRequirement"
    assert response.supportability.state == "READY"
    assert response.supportability.requirement_count == 1
    assert response.requirements[0].required_amount == Decimal("150000.0000")
    assert response.lineage["source_table"] == (
        "liquidity_reserve_requirements,portfolio_mandate_bindings"
    )
    service._reference_repository.list_liquidity_reserve_requirements.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=as_of_date,
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_requirements=False,
    )


@pytest.mark.asyncio
async def test_liquidity_reserve_requirement_marks_missing_requirement_incomplete():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_liquidity_reserve_requirements.return_value = []  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_liquidity_reserve_requirement(
        "PB_SG_GLOBAL_BAL_001",
        LiquidityReserveRequirementRequest(as_of_date=as_of_date, tenant_id="default"),
    )

    assert response is not None
    assert response.product_name == "LiquidityReserveRequirement"
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "LIQUIDITY_RESERVE_REQUIREMENT_EMPTY"
    assert response.supportability.missing_data_families == ["liquidity_reserve_requirement"]
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_liquidity_reserve_requirement_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_liquidity_reserve_requirement(
        "PB_MISSING",
        LiquidityReserveRequirementRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    service._reference_repository.list_liquidity_reserve_requirements.assert_not_awaited()  # type: ignore[attr-defined] # pylint: disable=line-too-long


@pytest.mark.asyncio
async def test_planned_withdrawal_schedule_returns_ready_source_records():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_planned_withdrawal_schedules.return_value = [  # type: ignore[attr-defined] # pylint: disable=line-too-long
        SimpleNamespace(
            withdrawal_schedule_id="WITHDRAWAL_Q3_001",
            withdrawal_type="PLANNED_WITHDRAWAL",
            withdrawal_status="active",
            amount=Decimal("50000.0000"),
            currency="SGD",
            scheduled_date=date(2026, 7, 15),
            recurrence_frequency="QUARTERLY",
            purpose_code="CLIENT_SPENDING",
            source_record_id="withdrawal:1",
            observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
            updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        )
    ]

    response = await service.get_planned_withdrawal_schedule(
        "PB_SG_GLOBAL_BAL_001",
        PlannedWithdrawalScheduleRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            horizon_days=180,
        ),
    )

    assert response is not None
    assert response.product_name == "PlannedWithdrawalSchedule"
    assert response.supportability.state == "READY"
    assert response.supportability.withdrawal_count == 1
    assert response.withdrawals[0].amount == Decimal("50000.0000")
    assert response.lineage["source_table"] == (
        "planned_withdrawal_schedules,portfolio_mandate_bindings"
    )
    service._reference_repository.list_planned_withdrawal_schedules.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=as_of_date,
        horizon_days=180,
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_withdrawals=False,
    )


@pytest.mark.asyncio
async def test_planned_withdrawal_schedule_marks_missing_withdrawals_incomplete():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )
    service._reference_repository.list_planned_withdrawal_schedules.return_value = []  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_planned_withdrawal_schedule(
        "PB_SG_GLOBAL_BAL_001",
        PlannedWithdrawalScheduleRequest(as_of_date=as_of_date, tenant_id="default"),
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "PLANNED_WITHDRAWAL_SCHEDULE_EMPTY"
    assert response.supportability.missing_data_families == ["planned_withdrawal_schedule"]
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_planned_withdrawal_schedule_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_planned_withdrawal_schedule(
        "PB_MISSING",
        PlannedWithdrawalScheduleRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    service._reference_repository.list_planned_withdrawal_schedules.assert_not_awaited()  # type: ignore[attr-defined] # pylint: disable=line-too-long


@pytest.mark.asyncio
async def test_external_hedge_execution_readiness_fails_closed_until_treasury_ingested():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )

    response = await service.get_external_hedge_execution_readiness(
        "PB_SG_GLOBAL_BAL_001",
        ExternalHedgeExecutionReadinessRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            reporting_currency="USD",
            exposure_currencies=["EUR", "JPY"],
        ),
    )

    assert response is not None
    assert response.product_name == "ExternalHedgeExecutionReadiness"
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"
    assert response.supportability.missing_data_families == [
        "external_currency_exposure",
        "external_hedge_policy",
        "external_fx_forward_curve",
        "external_eligible_hedge_instrument",
        "external_hedge_execution_readiness",
    ]
    assert "oms_acknowledgement" in response.supportability.blocked_capabilities
    assert response.readiness_checks == []
    assert response.data_quality_status == "MISSING"
    assert response.lineage == {
        "source_system": "external-bank-treasury",
        "source_table": "not_ingested",
        "contract_version": "rfc_039_external_hedge_execution_readiness_v1",
        "integration_status": "not_ingested",
        "runtime_posture": "fail_closed",
        "non_claims": (
            "hedge_advice,forward_pricing,counterparty_selection,best_execution,"
            "oms_acknowledgement,fills,settlement,autonomous_treasury_action"
        ),
    }
    service._reference_repository.resolve_discretionary_mandate_binding.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=as_of_date,
        mandate_id=None,
    )


@pytest.mark.asyncio
async def test_external_hedge_execution_readiness_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_external_hedge_execution_readiness(
        "PB_MISSING",
        ExternalHedgeExecutionReadinessRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None


@pytest.mark.asyncio
async def test_external_currency_exposure_fails_closed_until_treasury_ingested():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )

    response = await service.get_external_currency_exposure(
        "PB_SG_GLOBAL_BAL_001",
        ExternalCurrencyExposureRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            reporting_currency="USD",
            exposure_currencies=["EUR", "JPY"],
        ),
    )

    assert response is not None
    assert response.product_name == "ExternalCurrencyExposure"
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"
    assert response.supportability.exposure_count == 0
    assert response.supportability.missing_data_families == [
        "external_currency_exposure",
        "external_hedge_policy",
        "external_fx_forward_curve",
        "external_eligible_hedge_instrument",
    ]
    assert "fx_attribution" in response.supportability.blocked_capabilities
    assert "oms_acknowledgement" in response.supportability.blocked_capabilities
    assert response.exposures == []
    assert response.data_quality_status == "MISSING"
    assert response.lineage == {
        "source_system": "external-bank-treasury",
        "source_table": "not_ingested",
        "contract_version": "rfc_039_external_currency_exposure_v1",
        "integration_status": "not_ingested",
        "runtime_posture": "fail_closed",
        "non_claims": (
            "fx_attribution,hedge_advice,treasury_instruction,execution_readiness,"
            "oms_acknowledgement,fills,settlement,autonomous_treasury_action"
        ),
    }
    service._reference_repository.resolve_discretionary_mandate_binding.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=as_of_date,
        mandate_id=None,
    )


@pytest.mark.asyncio
async def test_external_currency_exposure_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_external_currency_exposure(
        "PB_MISSING",
        ExternalCurrencyExposureRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None


@pytest.mark.asyncio
async def test_external_hedge_policy_fails_closed_until_treasury_ingested():
    service = make_service()
    as_of_date = date(2026, 5, 3)
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (  # type: ignore[attr-defined] # pylint: disable=line-too-long
        profile_binding_row(as_of_date)
    )

    response = await service.get_external_hedge_policy(
        "PB_SG_GLOBAL_BAL_001",
        ExternalHedgePolicyRequest(
            as_of_date=as_of_date,
            tenant_id="default",
            reporting_currency="USD",
            exposure_currencies=["EUR", "JPY"],
        ),
    )

    assert response is not None
    assert response.product_name == "ExternalHedgePolicy"
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"
    assert response.supportability.policy_rule_count == 0
    assert response.supportability.missing_data_families == ["external_hedge_policy"]
    assert "hedge_policy_approval" in response.supportability.blocked_capabilities
    assert "treasury_instruction" in response.supportability.blocked_capabilities
    assert "oms_acknowledgement" in response.supportability.blocked_capabilities
    assert response.policy_rules == []
    assert response.data_quality_status == "MISSING"
    assert response.lineage == {
        "source_system": "external-bank-treasury",
        "source_table": "not_ingested",
        "contract_version": "rfc_039_external_hedge_policy_v1",
        "integration_status": "not_ingested",
        "runtime_posture": "fail_closed",
        "non_claims": (
            "hedge_policy_approval,hedge_advice,treasury_instruction,"
            "counterparty_selection,order_generation,best_execution,oms_acknowledgement,"
            "fills,settlement,autonomous_treasury_action"
        ),
    }
    service._reference_repository.resolve_discretionary_mandate_binding.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=line-too-long
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=as_of_date,
        mandate_id=None,
    )


@pytest.mark.asyncio
async def test_external_hedge_policy_returns_none_without_binding():
    service = make_service()
    service._reference_repository = AsyncMock()  # pylint: disable=protected-access
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None  # type: ignore[attr-defined] # pylint: disable=line-too-long

    response = await service.get_external_hedge_policy(
        "PB_MISSING",
        ExternalHedgePolicyRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None


@pytest.mark.parametrize(
    ("coverage", "expected_status"),
    [
        (
            {
                "total_points": 3,
                "observed_dates": [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
                "quality_status_counts": {"accepted": 3},
            },
            COMPLETE,
        ),
        (
            {
                "total_points": 3,
                "observed_dates": [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
                "quality_status_counts": {"STALE": 1, "accepted": 2},
            },
            STALE,
        ),
        (
            {
                "total_points": 0,
                "observed_dates": [],
                "quality_status_counts": {},
            },
            UNRECONCILED,
        ),
    ],
)
def test_to_coverage_response_classifies_data_quality_status(
    coverage: dict[str, object],
    expected_status: str,
) -> None:
    response = IntegrationService._to_coverage_response(  # pylint: disable=protected-access
        coverage=coverage,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.data_quality_status == expected_status


def test_to_coverage_response_carries_latest_evidence_timestamp() -> None:
    latest_evidence_timestamp = datetime(2026, 1, 3, 14, 30, tzinfo=UTC)

    response = IntegrationService._to_coverage_response(  # pylint: disable=protected-access
        coverage={
            "total_points": 3,
            "observed_dates": [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
            "quality_status_counts": {"accepted": 3},
            "latest_evidence_timestamp": latest_evidence_timestamp,
        },
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.latest_evidence_timestamp == latest_evidence_timestamp


def test_market_reference_data_quality_classifies_reference_rows() -> None:
    rows = [
        SimpleNamespace(quality_status="accepted"),
        SimpleNamespace(quality_status="estimated"),
        SimpleNamespace(quality_status="accepted"),
    ]

    assert (
        IntegrationService._market_reference_data_quality_status(  # pylint: disable=protected-access
            rows,
            required_count=len(rows),
        )
        == PARTIAL
    )
    assert (
        IntegrationService._market_reference_data_quality_status(  # pylint: disable=protected-access
            [SimpleNamespace(quality_status="blocked")],
            required_count=1,
        )
        == BLOCKED
    )
    assert (
        IntegrationService._market_reference_data_quality_status(  # pylint: disable=protected-access
            [SimpleNamespace()],
            required_count=1,
        )
        == "UNKNOWN"
    )


def test_latest_reference_evidence_timestamp_uses_durable_reference_timestamps() -> None:
    older_source_timestamp = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    latest_updated_at = datetime(2026, 1, 3, 11, 0, tzinfo=UTC)

    assert (
        IntegrationService._latest_reference_evidence_timestamp(  # pylint: disable=protected-access
            [
                SimpleNamespace(source_timestamp=older_source_timestamp),
                SimpleNamespace(updated_at=latest_updated_at),
            ]
        )
        == latest_updated_at
    )


@pytest.mark.asyncio
async def test_resolve_model_portfolio_targets_returns_ready_supportability() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    observed_at = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    service._reference_repository.resolve_model_portfolio_definition.return_value = SimpleNamespace(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        model_portfolio_version="2026.03",
        display_name="Singapore Balanced DPM Model",
        base_currency="SGD",
        risk_profile="balanced",
        mandate_type="discretionary",
        rebalance_frequency="monthly",
        approval_status="approved",
        approved_at=observed_at,
        effective_from=date(2026, 3, 25),
        effective_to=None,
        source_system="investment_office_model_system",
        source_record_id="model_sg_balanced_202603",
        observed_at=observed_at,
    )
    service._reference_repository.list_model_portfolio_targets.return_value = [
        SimpleNamespace(
            instrument_id="EQ_US_AAPL",
            target_weight=Decimal("0.6000000000"),
            min_weight=Decimal("0.5500000000"),
            max_weight=Decimal("0.6500000000"),
            target_status="active",
            quality_status="accepted",
            source_record_id="target_aapl",
            observed_at=observed_at,
        ),
        SimpleNamespace(
            instrument_id="FI_US_TREASURY_10Y",
            target_weight=Decimal("0.4000000000"),
            min_weight=Decimal("0.3500000000"),
            max_weight=Decimal("0.4500000000"),
            target_status="active",
            quality_status="accepted",
            source_record_id="target_tsy",
            observed_at=observed_at,
        ),
    ]

    response = await service.resolve_model_portfolio_targets(
        "MODEL_SG_BALANCED_DPM",
        request=model_portfolio_target_request(as_of_date=date(2026, 3, 31)),
    )

    assert response is not None
    assert response.product_name == "DpmModelPortfolioTarget"
    assert response.model_portfolio_version == "2026.03"
    assert response.supportability.state == "READY"
    assert response.supportability.total_target_weight == Decimal("1.0000000000")
    assert [target.instrument_id for target in response.targets] == [
        "EQ_US_AAPL",
        "FI_US_TREASURY_10Y",
    ]
    assert response.lineage["source_system"] == "investment_office_model_system"
    assert response.latest_evidence_timestamp == observed_at
    service._reference_repository.list_model_portfolio_targets.assert_awaited_once_with(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        model_portfolio_version="2026.03",
        as_of_date=date(2026, 3, 31),
        include_inactive_targets=False,
    )


@pytest.mark.asyncio
async def test_resolve_model_portfolio_targets_maps_missing_definition_to_none() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    service._reference_repository.resolve_model_portfolio_definition.return_value = None

    response = await service.resolve_model_portfolio_targets(
        "MODEL_MISSING",
        request=model_portfolio_target_request(as_of_date=date(2026, 3, 31)),
    )

    assert response is None
    service._reference_repository.list_model_portfolio_targets.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_model_portfolio_targets_degrades_when_weights_do_not_sum_to_one() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    service._reference_repository.resolve_model_portfolio_definition.return_value = SimpleNamespace(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        model_portfolio_version="2026.03",
        display_name="Singapore Balanced DPM Model",
        base_currency="SGD",
        risk_profile="balanced",
        mandate_type="discretionary",
        rebalance_frequency="monthly",
        approval_status="approved",
        approved_at=None,
        effective_from=date(2026, 3, 25),
        effective_to=None,
        source_system="investment_office_model_system",
        source_record_id="model_sg_balanced_202603",
        observed_at=None,
    )
    service._reference_repository.list_model_portfolio_targets.return_value = [
        SimpleNamespace(
            instrument_id="EQ_US_AAPL",
            target_weight=Decimal("0.5000000000"),
            min_weight=None,
            max_weight=None,
            target_status="active",
            quality_status="accepted",
            source_record_id="target_aapl",
        )
    ]

    response = await service.resolve_model_portfolio_targets(
        "MODEL_SG_BALANCED_DPM",
        request=model_portfolio_target_request(as_of_date=date(2026, 3, 31)),
    )

    assert response is not None
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MODEL_TARGET_WEIGHTS_NOT_ONE"
    assert response.supportability.total_target_weight == Decimal("0.5000000000")


@pytest.mark.asyncio
async def test_resolve_discretionary_mandate_binding_returns_ready_binding() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    observed_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_000184",
            mandate_type="discretionary",
            discretionary_authority_status="active",
            booking_center_code="Singapore",
            jurisdiction_code="SG",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            policy_pack_id="POLICY_DPM_SG_BALANCED_V1",
            mandate_objective=(
                "Preserve and grow global balanced wealth within controlled drawdown limits."
            ),
            risk_profile="balanced",
            investment_horizon="long_term",
            review_cadence="quarterly",
            last_review_date=date(2026, 3, 31),
            next_review_due_date=date(2026, 6, 30),
            leverage_allowed=False,
            tax_awareness_allowed=True,
            settlement_awareness_required=True,
            rebalance_frequency="monthly",
            rebalance_bands={
                "default_band": "0.0250000000",
                "cash_reserve_weight": "0.0200000000",
            },
            effective_from=date(2026, 4, 1),
            effective_to=None,
            binding_version=1,
            source_system="mandate_admin",
            source_record_id="mandate_001_v1",
            observed_at=observed_at,
            quality_status="accepted",
        )
    )

    response = await service.resolve_discretionary_mandate_binding(
        "PB_SG_GLOBAL_BAL_001",
        request=mandate_binding_request(date(2026, 4, 10)),
    )

    assert response is not None
    assert response.product_name == "DiscretionaryMandateBinding"
    assert response.model_portfolio_id == "MODEL_PB_SG_GLOBAL_BAL_DPM"
    assert response.policy_pack_id == "POLICY_DPM_SG_BALANCED_V1"
    assert response.mandate_objective == (
        "Preserve and grow global balanced wealth within controlled drawdown limits."
    )
    assert response.review_cadence == "quarterly"
    assert response.last_review_date == date(2026, 3, 31)
    assert response.next_review_due_date == date(2026, 6, 30)
    assert response.rebalance_bands.default_band == Decimal("0.0250000000")
    assert response.rebalance_bands.cash_reserve_weight == Decimal("0.0200000000")
    assert response.supportability.state == "READY"
    assert response.supportability.missing_data_families == []
    assert response.latest_evidence_timestamp == observed_at
    service._reference_repository.resolve_discretionary_mandate_binding.assert_awaited_once_with(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=date(2026, 4, 10),
        mandate_id=None,
        booking_center_code=None,
    )


@pytest.mark.asyncio
async def test_resolve_discretionary_mandate_binding_blocks_inactive_authority() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_000184",
            mandate_type="discretionary",
            discretionary_authority_status="suspended",
            booking_center_code="Singapore",
            jurisdiction_code="SG",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            policy_pack_id="POLICY_DPM_SG_BALANCED_V1",
            mandate_objective=(
                "Preserve and grow global balanced wealth within controlled drawdown limits."
            ),
            risk_profile="balanced",
            investment_horizon="long_term",
            review_cadence="quarterly",
            last_review_date=date(2026, 3, 31),
            next_review_due_date=date(2026, 6, 30),
            leverage_allowed=False,
            tax_awareness_allowed=True,
            settlement_awareness_required=True,
            rebalance_frequency="monthly",
            rebalance_bands={"default_band": "0.0250000000"},
            effective_from=date(2026, 4, 1),
            effective_to=None,
            binding_version=1,
            source_system="mandate_admin",
            source_record_id="mandate_001_v1",
            observed_at=None,
            quality_status="accepted",
        )
    )

    response = await service.resolve_discretionary_mandate_binding(
        "PB_SG_GLOBAL_BAL_001",
        request=mandate_binding_request(date(2026, 4, 10)),
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "DISCRETIONARY_AUTHORITY_NOT_ACTIVE"
    assert response.supportability.missing_data_families == ["active_discretionary_authority"]


@pytest.mark.asyncio
async def test_resolve_mandate_binding_flags_missing_objective_and_review_schedule() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_000184",
            mandate_type="discretionary",
            discretionary_authority_status="active",
            booking_center_code="Singapore",
            jurisdiction_code="SG",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            policy_pack_id="POLICY_DPM_SG_BALANCED_V1",
            mandate_objective=None,
            risk_profile="balanced",
            investment_horizon="long_term",
            review_cadence=None,
            last_review_date=None,
            next_review_due_date=None,
            leverage_allowed=False,
            tax_awareness_allowed=True,
            settlement_awareness_required=True,
            rebalance_frequency="monthly",
            rebalance_bands={"default_band": "0.0250000000"},
            effective_from=date(2026, 4, 1),
            effective_to=None,
            binding_version=1,
            source_system="mandate_admin",
            source_record_id="mandate_001_v1",
            observed_at=None,
            quality_status="accepted",
        )
    )

    response = await service.resolve_discretionary_mandate_binding(
        "PB_SG_GLOBAL_BAL_001",
        request=mandate_binding_request(date(2026, 4, 10)),
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MANDATE_OBJECTIVE_MISSING"
    assert response.supportability.missing_data_families == [
        "mandate_objective",
        "mandate_review_schedule",
    ]


@pytest.mark.asyncio
async def test_resolve_discretionary_mandate_binding_degrades_overdue_review() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = (
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_000184",
            mandate_type="discretionary",
            discretionary_authority_status="active",
            booking_center_code="Singapore",
            jurisdiction_code="SG",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            policy_pack_id="POLICY_DPM_SG_BALANCED_V1",
            mandate_objective="Balanced discretionary growth",
            risk_profile="balanced",
            investment_horizon="long_term",
            review_cadence="quarterly",
            last_review_date=date(2026, 1, 31),
            next_review_due_date=date(2026, 3, 31),
            leverage_allowed=False,
            tax_awareness_allowed=True,
            settlement_awareness_required=True,
            rebalance_frequency="monthly",
            rebalance_bands={"default_band": "0.0250000000"},
            effective_from=date(2026, 1, 1),
            effective_to=None,
            binding_version=1,
            source_system="mandate_admin",
            source_record_id="mandate_001_v1",
            observed_at=None,
            quality_status="accepted",
        )
    )

    response = await service.resolve_discretionary_mandate_binding(
        "PB_SG_GLOBAL_BAL_001",
        request=mandate_binding_request(date(2026, 4, 10)),
    )

    assert response is not None
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MANDATE_REVIEW_OVERDUE"


@pytest.mark.asyncio
async def test_resolve_discretionary_mandate_binding_maps_missing_row_to_none() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    service._reference_repository.resolve_discretionary_mandate_binding.return_value = None

    response = await service.resolve_discretionary_mandate_binding(
        "PB_SG_GLOBAL_BAL_001",
        request=mandate_binding_request(date(2026, 4, 10)),
    )

    assert response is None


@pytest.mark.asyncio
async def test_resolve_instrument_eligibility_bulk_preserves_order_and_unknown_records() -> None:
    service = make_service()
    service._reference_repository = AsyncMock()  # type: ignore[method-assign]
    observed_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    service._reference_repository.list_instrument_eligibility_profiles.return_value = [
        SimpleNamespace(
            security_id="MSFT",
            eligibility_status="RESTRICTED",
            product_shelf_status="RESTRICTED",
            buy_allowed=False,
            sell_allowed=True,
            restriction_reason_codes=["CONCENTRATION_REVIEW"],
            settlement_days=2,
            settlement_calendar_id="US_NYSE",
            liquidity_tier="L1",
            issuer_id="MICROSOFT",
            issuer_name="Microsoft Corporation",
            ultimate_parent_issuer_id="MICROSOFT_PARENT",
            ultimate_parent_issuer_name="Microsoft Corporation",
            asset_class="Equity",
            country_of_risk="US",
            effective_from=date(2026, 4, 1),
            effective_to=None,
            source_record_id="MSFT-elig",
            observed_at=observed_at,
            quality_status="accepted",
        ),
        SimpleNamespace(
            security_id="AAPL",
            eligibility_status="APPROVED",
            product_shelf_status="APPROVED",
            buy_allowed=True,
            sell_allowed=True,
            restriction_reason_codes=[],
            settlement_days=2,
            settlement_calendar_id="US_NYSE",
            liquidity_tier="L1",
            issuer_id="APPLE",
            issuer_name="Apple Inc.",
            ultimate_parent_issuer_id="APPLE_PARENT",
            ultimate_parent_issuer_name="Apple Inc.",
            asset_class="Equity",
            country_of_risk="US",
            effective_from=date(2026, 4, 1),
            effective_to=None,
            source_record_id="AAPL-elig",
            observed_at=observed_at,
            quality_status="accepted",
        ),
    ]

    response = await service.resolve_instrument_eligibility_bulk(
        instrument_eligibility_request(
            ["AAPL", "UNKNOWN_SEC", "MSFT"],
            date(2026, 4, 10),
        )
    )

    assert response.product_name == "InstrumentEligibilityProfile"
    assert [record.security_id for record in response.records] == [
        "AAPL",
        "UNKNOWN_SEC",
        "MSFT",
    ]
    assert response.records[0].buy_allowed is True
    assert response.records[1].found is False
    assert response.records[1].restriction_reason_codes == ["ELIGIBILITY_PROFILE_MISSING"]
    assert response.records[2].restriction_reason_codes == ["CONCENTRATION_REVIEW"]
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "INSTRUMENT_ELIGIBILITY_MISSING"
    assert response.supportability.requested_count == 3
    assert response.supportability.resolved_count == 2
    assert response.supportability.missing_security_ids == ["UNKNOWN_SEC"]
    assert response.latest_evidence_timestamp == observed_at
    service._reference_repository.list_instrument_eligibility_profiles.assert_awaited_once_with(
        security_ids=["AAPL", "UNKNOWN_SEC", "MSFT"],
        as_of_date=date(2026, 4, 10),
    )


def test_canonical_consumer_system_mappings() -> None:
    service = make_service()
    assert service._canonical_consumer_system("lotus-manage") == "lotus-manage"
    assert service._canonical_consumer_system("lotus-gateway") == "lotus-gateway"
    assert service._canonical_consumer_system("UI") == "UI"
    assert service._canonical_consumer_system("Custom-System") == "custom-system"
    assert service._canonical_consumer_system(None) == "unknown"
    assert service._canonical_consumer_system("   ") == "unknown"


def test_load_policy_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()

    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    assert service._load_policy() == {}

    monkeypatch.setenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", "not-json")
    assert service._load_policy() == {}

    monkeypatch.setenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", '["bad"]')
    assert service._load_policy() == {}

    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"strict_mode": true, "consumers": {"lotus-manage": ["OVERVIEW"]}}',
    )
    loaded = service._load_policy()
    assert loaded["strict_mode"] is True
    assert "consumers" in loaded


def test_normalize_and_resolve_consumer_sections() -> None:
    service = make_service()
    assert service._normalize_sections(None) is None
    assert service._normalize_sections([" overview ", "HOLDINGS", "", 123]) == [
        "OVERVIEW",
        "HOLDINGS",
    ]

    sections, key = service._resolve_consumer_sections(None, "lotus-manage")
    assert sections is None
    assert key is None

    sections, key = service._resolve_consumer_sections(
        {"lotus-manage": ["overview"], "other": ["x"]},
        "lotus-manage",
    )
    assert sections == ["OVERVIEW"]
    assert key == "lotus-manage"

    sections, key = service._resolve_consumer_sections({"foo": ["x"]}, "lotus-manage")
    assert sections is None
    assert key is None


def test_resolve_policy_context_default(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    monkeypatch.delenv("LOTUS_CORE_POLICY_VERSION", raising=False)

    ctx = service._resolve_policy_context(tenant_id="default", consumer_system="lotus-manage")
    assert ctx.policy_version == "tenant-default-v1"
    assert ctx.policy_source == "default"
    assert ctx.matched_rule_id == "default"
    assert ctx.strict_mode is False
    assert ctx.allowed_sections is None
    assert "NO_ALLOWED_SECTION_RESTRICTION" in ctx.warnings


def test_resolve_policy_context_global_and_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"strict_mode":false,'
            '"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]},'
            '"tenants":{"tenant-a":{"strict_mode":true,"consumers":{"lotus-manage":["ALLOCATION"]}}}}'
        ),
    )
    monkeypatch.setenv("LOTUS_CORE_POLICY_VERSION", "tenant-v7")

    global_ctx = service._resolve_policy_context(
        tenant_id="default",
        consumer_system="lotus-manage",
    )
    assert global_ctx.policy_source == "global"
    assert global_ctx.matched_rule_id == "global.consumers.lotus-manage"
    assert global_ctx.strict_mode is False
    assert global_ctx.allowed_sections == ["OVERVIEW", "HOLDINGS"]

    tenant_ctx = service._resolve_policy_context(
        tenant_id="tenant-a",
        consumer_system="lotus-manage",
    )
    assert tenant_ctx.policy_version == "tenant-v7"
    assert tenant_ctx.policy_source == "tenant"
    assert tenant_ctx.matched_rule_id == "tenant.tenant-a.consumers.lotus-manage"
    assert tenant_ctx.strict_mode is True
    assert tenant_ctx.allowed_sections == ["ALLOCATION"]


def test_resolve_policy_context_tenant_default_sections_and_strict_mode_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"tenants":{"tenant-x":{"strict_mode":true,"default_sections":["OVERVIEW"]},'
            '"tenant-y":{"strict_mode":true}}}'
        ),
    )

    tenant_default_ctx = service._resolve_policy_context(
        tenant_id="tenant-x",
        consumer_system="lotus-manage",
    )
    assert tenant_default_ctx.policy_source == "tenant"
    assert tenant_default_ctx.matched_rule_id == "tenant.tenant-x.default_sections"
    assert tenant_default_ctx.allowed_sections == ["OVERVIEW"]
    assert tenant_default_ctx.strict_mode is True

    strict_only_ctx = service._resolve_policy_context(
        tenant_id="tenant-y",
        consumer_system="lotus-manage",
    )
    assert strict_only_ctx.policy_source == "tenant"
    assert strict_only_ctx.matched_rule_id == "tenant.tenant-y.strict_mode"
    assert strict_only_ctx.allowed_sections is None
    assert strict_only_ctx.strict_mode is True


def test_get_effective_policy_filters_requested_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]}}',
    )

    response = service.get_effective_policy(
        consumer_system="lotus-manage",
        tenant_id="default",
        include_sections=["overview", "allocation", "holdings"],
    )
    assert response.consumer_system == "lotus-manage"
    assert response.allowed_sections == ["OVERVIEW", "HOLDINGS"]
    assert response.policy_provenance.matched_rule_id == "global.consumers.lotus-manage"


def test_get_effective_policy_no_allowed_restriction_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)

    response = service.get_effective_policy(
        consumer_system="custom-client",
        tenant_id="default",
        include_sections=["overview", "allocation"],
    )
    assert response.consumer_system == "custom-client"
    assert response.allowed_sections == ["OVERVIEW", "ALLOCATION"]
    assert "NO_ALLOWED_SECTION_RESTRICTION" in response.warnings


def test_get_effective_policy_uses_configured_allowed_sections_when_unrequested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-manage":["HOLDINGS","ALLOCATION"]}}',
    )

    response = service.get_effective_policy(
        consumer_system="lotus-manage",
        tenant_id="default",
        include_sections=None,
    )

    assert response.consumer_system == "lotus-manage"
    assert response.allowed_sections == ["HOLDINGS", "ALLOCATION"]


@pytest.mark.asyncio
async def test_reference_contract_methods() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        resolve_benchmark_assignment=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                benchmark_id="B1",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                assignment_source="policy",
                assignment_status="active",
                policy_pack_id="pack",
                source_system="lotus-manage",
                assignment_recorded_at=date(2026, 1, 1),
                assignment_version=1,
            )
        ),
        get_benchmark_definition=AsyncMock(
            return_value=SimpleNamespace(
                benchmark_id="B1",
                benchmark_name="Benchmark 1",
                benchmark_type="composite",
                benchmark_currency="USD",
                return_convention="total_return_index",
                benchmark_status="active",
                benchmark_family="family",
                benchmark_provider="provider",
                rebalance_frequency="monthly",
                classification_set_id="set1",
                classification_labels={"asset_class": "equity"},
                effective_from=date(2026, 1, 1),
                effective_to=None,
                quality_status="accepted",
                source_timestamp=None,
                source_vendor="vendor",
                source_record_id="src1",
            )
        ),
        list_benchmark_definitions_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    benchmark_id="B1",
                    benchmark_currency="USD",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_components=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                    rebalance_event_id="r1",
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=date(2026, 3, 31),
                    rebalance_event_id="r1",
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_components_for_benchmarks=AsyncMock(
            return_value={
                "B1": [
                    SimpleNamespace(
                        index_id="IDX1",
                        composition_weight=Decimal("0.5"),
                        composition_effective_from=date(2026, 1, 1),
                        composition_effective_to=None,
                        rebalance_event_id="r1",
                        quality_status="accepted",
                    )
                ]
            }
        ),
        list_benchmark_definitions=AsyncMock(return_value=[]),
        list_index_definitions=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    index_name="Index 1",
                    index_currency="USD",
                    index_type="equity",
                    index_status="active",
                    index_provider="provider",
                    index_market="global",
                    classification_set_id="set1",
                    classification_labels={"sector": "technology"},
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                    source_timestamp=None,
                    source_vendor="vendor",
                    source_record_id="idx-src",
                )
            ]
        ),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        list_index_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    series_date=date(2026, 1, 1),
                    index_return=Decimal("0.01"),
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    benchmark_return=Decimal("0.008"),
                    return_period="1d",
                    return_convention="total_return_index",
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        get_fx_rates=AsyncMock(return_value={date(2026, 1, 1): Decimal("1.1")}),
        list_index_price_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    value_convention="close_price",
                    quality_status="accepted",
                )
            ]
        ),
        list_index_return_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    index_return=Decimal("0.01"),
                    return_period="1d",
                    return_convention="total_return_index",
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        list_risk_free_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    value=Decimal("0.03"),
                    value_convention="annualized_rate",
                    day_count_convention="act_360",
                    compounding_convention="simple",
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        get_benchmark_coverage=AsyncMock(
            return_value={
                "total_points": 10,
                "observed_start_date": date(2026, 1, 1),
                "observed_end_date": date(2026, 1, 3),
                "quality_status_counts": {"accepted": 10},
            }
        ),
        get_risk_free_coverage=AsyncMock(
            return_value={
                "total_points": 10,
                "observed_start_date": date(2026, 1, 1),
                "observed_end_date": date(2026, 1, 3),
                "quality_status_counts": {"accepted": 10},
            }
        ),
        list_taxonomy=AsyncMock(
            return_value=[
                SimpleNamespace(
                    classification_set_id="set1",
                    taxonomy_scope="index",
                    dimension_name="sector",
                    dimension_value="technology",
                    dimension_description="desc",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                )
            ]
        ),
    )

    assignment = await service.resolve_benchmark_assignment("P1", date(2026, 1, 1))
    assert assignment is not None
    assert assignment.benchmark_id == "B1"
    assert assignment.product_name == "BenchmarkAssignment"
    assert assignment.generated_at.tzinfo is not None
    assert assignment.restatement_version == "current"
    assert assignment.reconciliation_status == "UNKNOWN"
    assert assignment.data_quality_status == "COMPLETE"

    definition = await service.get_benchmark_definition("B1", date(2026, 1, 1))
    assert definition is not None
    assert definition.benchmark_id == "B1"

    composition_window = await service.get_benchmark_composition_window(
        "B1",
        SimpleNamespace(
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
        ),
    )
    assert composition_window is not None
    assert composition_window.benchmark_currency == "USD"
    assert composition_window.segments[0].index_id == "IDX1"
    assert composition_window.product_name == "BenchmarkConstituentWindow"
    assert composition_window.as_of_date == date(2026, 3, 31)

    benchmark_catalog = await service.list_benchmark_catalog(date(2026, 1, 1), None, None, None)
    assert benchmark_catalog.records == []

    index_catalog = await service.list_index_catalog(date(2026, 1, 1), [], None, None, None)
    assert index_catalog.records[0].index_id == "IDX1"

    market_series = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "index_return", "benchmark_return", "component_weight"],
        ),
    )
    assert market_series.component_series
    assert market_series.benchmark_currency == "USD"
    assert market_series.target_currency == "USD"
    assert (
        market_series.normalization_status
        == "native_component_series_with_identity_benchmark_to_target_fx_context"
    )
    assert (
        market_series.normalization_policy
        == "native_component_series_downstream_normalization_required"
    )
    assert market_series.component_series[0].points[0].series_currency == "USD"
    assert market_series.request_fingerprint
    assert market_series.page.page_size == 250
    assert market_series.page.sort_key == "index_id:asc"
    assert market_series.page.returned_component_count == 1
    assert market_series.page.request_scope_fingerprint == market_series.request_fingerprint
    assert market_series.page.next_page_token is None
    assert market_series.product_name == "MarketDataWindow"
    assert market_series.as_of_date == date(2026, 1, 1)
    assert market_series.reconciliation_status == "UNKNOWN"
    assert market_series.data_quality_status == COMPLETE

    index_price = await service.get_index_price_series(
        index_id="IDX1",
        request=SimpleNamespace(
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert index_price.points
    assert index_price.product_name == "IndexSeriesWindow"
    assert index_price.as_of_date == date(2026, 1, 2)

    index_return = await service.get_index_return_series(
        index_id="IDX1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert index_return.points
    assert index_return.as_of_date == date(2026, 1, 1)
    assert index_return.request_fingerprint
    assert index_return.product_name == "IndexSeriesWindow"

    benchmark_return = await service.get_benchmark_return_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert benchmark_return.points
    assert benchmark_return.as_of_date == date(2026, 1, 1)
    assert benchmark_return.request_fingerprint

    risk_free = await service.get_risk_free_series(
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            currency="USD",
            series_mode="annualized_rate_series",
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert risk_free.points
    assert risk_free.as_of_date == date(2026, 1, 1)
    assert risk_free.request_fingerprint
    assert risk_free.product_name == "RiskFreeSeriesWindow"

    coverage = await service.get_benchmark_coverage("B1", date(2026, 1, 1), date(2026, 1, 3))
    assert coverage.total_points == 10
    assert coverage.request_fingerprint
    assert coverage.product_name == "DataQualityCoverageReport"
    assert coverage.as_of_date == date(2026, 1, 3)

    rf_coverage = await service.get_risk_free_coverage("USD", date(2026, 1, 1), date(2026, 1, 3))
    assert rf_coverage.total_points == 10
    assert rf_coverage.request_fingerprint
    assert rf_coverage.product_name == "DataQualityCoverageReport"
    assert rf_coverage.as_of_date == date(2026, 1, 3)

    taxonomy = await service.get_classification_taxonomy(as_of_date=date(2026, 1, 1))
    assert taxonomy.records[0].dimension_name == "sector"
    assert taxonomy.request_fingerprint
    assert taxonomy.product_name == "InstrumentReferenceBundle"
    assert taxonomy.restatement_version == "current"


@pytest.mark.asyncio
async def test_market_reference_products_expose_row_backed_quality_and_evidence_timestamp() -> None:
    service = make_service()
    older_source_timestamp = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    latest_source_timestamp = datetime(2026, 1, 3, 11, 15, tzinfo=UTC)
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        list_index_price_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 2),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    value_convention="close_price",
                    quality_status="accepted",
                    source_timestamp=older_source_timestamp,
                ),
                SimpleNamespace(
                    series_date=date(2026, 1, 3),
                    index_price=Decimal("101"),
                    series_currency="USD",
                    value_convention="close_price",
                    quality_status="estimated",
                    source_timestamp=latest_source_timestamp,
                ),
            ]
        )
    )

    response = await service.get_index_price_series(
        index_id="IDX1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 3),
            window=SimpleNamespace(start_date=date(2026, 1, 2), end_date=date(2026, 1, 3)),
            frequency="daily",
        ),
    )

    assert response.product_name == "IndexSeriesWindow"
    assert response.data_quality_status == PARTIAL
    assert response.latest_evidence_timestamp == latest_source_timestamp
    assert response.source_batch_fingerprint is None
    assert response.snapshot_id is None


@pytest.mark.asyncio
async def test_reference_contract_none_and_fx_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        resolve_benchmark_assignment=AsyncMock(return_value=None),
        get_benchmark_definition=AsyncMock(
            side_effect=[
                None,
                SimpleNamespace(benchmark_currency="EUR"),
                SimpleNamespace(benchmark_currency="EUR"),
            ]
        ),
        list_benchmark_definitions_overlapping_window=AsyncMock(return_value=[]),
        list_benchmark_components=AsyncMock(return_value=[]),
        list_benchmark_components_overlapping_window=AsyncMock(return_value=[]),
        list_benchmark_components_for_benchmarks=AsyncMock(return_value={}),
        list_benchmark_definitions=AsyncMock(
            return_value=[
                SimpleNamespace(
                    benchmark_id="B1",
                    benchmark_name="Benchmark 1",
                    benchmark_type="single_index",
                    benchmark_currency="EUR",
                    return_convention="total_return_index",
                    benchmark_status="active",
                    benchmark_family=None,
                    benchmark_provider=None,
                    rebalance_frequency=None,
                    classification_set_id=None,
                    classification_labels={},
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                    source_timestamp=None,
                    source_vendor=None,
                    source_record_id=None,
                )
            ]
        ),
        list_index_definitions=AsyncMock(return_value=[]),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
        list_index_price_series=AsyncMock(return_value=[]),
        list_index_return_series=AsyncMock(return_value=[]),
        list_risk_free_series=AsyncMock(return_value=[]),
        get_benchmark_coverage=AsyncMock(
            return_value={
                "total_points": 0,
                "observed_start_date": None,
                "observed_end_date": None,
                "quality_status_counts": {},
            }
        ),
        get_risk_free_coverage=AsyncMock(
            return_value={
                "total_points": 0,
                "observed_start_date": None,
                "observed_end_date": None,
                "quality_status_counts": {},
            }
        ),
        list_taxonomy=AsyncMock(return_value=[]),
    )

    assert await service.resolve_benchmark_assignment("P1", date(2026, 1, 1)) is None
    assert await service.get_benchmark_definition("B1", date(2026, 1, 1)) is None
    assert (
        await service.get_benchmark_composition_window(
            "B1",
            SimpleNamespace(
                window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
            ),
        )
        is None
    )

    benchmark_catalog = await service.list_benchmark_catalog(
        date(2026, 1, 1), "single_index", "EUR", "active"
    )
    assert benchmark_catalog.records

    await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "fx_rate"],
        ),
    )
    service._reference_repository.get_fx_rates.assert_awaited_once()
    benchmark_market_series = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price"],
        ),
    )
    assert benchmark_market_series.benchmark_currency == "EUR"
    assert benchmark_market_series.target_currency == "USD"
    assert (
        benchmark_market_series.normalization_status
        == "native_component_series_without_fx_context_request"
    )
    assert benchmark_market_series.fx_context_source_currency == "EUR"
    assert benchmark_market_series.fx_context_target_currency == "USD"

    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"tenants":{"tenant-z":{"strict_mode":false,"default_sections":["OVERVIEW"]}}}',
    )
    ctx = service._resolve_policy_context("tenant-z", "lotus-manage")
    assert ctx.policy_source == "tenant"
    assert ctx.matched_rule_id == "tenant.tenant-z.default_sections"

    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    effective = service.get_effective_policy(
        consumer_system="lotus-manage",
        tenant_id="default",
        include_sections=None,
    )
    assert effective.allowed_sections == []


@pytest.mark.asyncio
async def test_benchmark_composition_window_rejects_currency_changes_within_window() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        list_benchmark_definitions_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(benchmark_currency="USD"),
                SimpleNamespace(benchmark_currency="EUR"),
            ]
        ),
        list_benchmark_components_overlapping_window=AsyncMock(return_value=[]),
    )

    with pytest.raises(ValueError, match="currency changed within requested composition window"):
        await service.get_benchmark_composition_window(
            "B1",
            SimpleNamespace(
                window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
            ),
        )


@pytest.mark.asyncio
async def test_benchmark_market_series_supports_paging_tokens() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX2",
                    composition_weight=Decimal("0.3"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX3",
                    composition_weight=Decimal("0.2"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
    )

    first_page = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=2, page_token=None),
        ),
    )
    assert [row.index_id for row in first_page.component_series] == ["IDX1", "IDX2"]
    assert first_page.page.returned_component_count == 2
    assert first_page.page.next_page_token is not None

    second_page = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=2, page_token=first_page.page.next_page_token),
        ),
    )
    assert [row.index_id for row in second_page.component_series] == ["IDX3"]
    assert second_page.page.returned_component_count == 1
    assert second_page.page.next_page_token is None


@pytest.mark.asyncio
async def test_benchmark_market_series_quality_summary_is_page_scoped() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX2",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    index_id="IDX2",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("200"),
                    series_currency="USD",
                    quality_status="estimated",
                ),
            ]
        ),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=1, page_token=None),
        ),
    )

    assert [row.index_id for row in response.component_series] == ["IDX1"]
    assert response.quality_status_summary == {"accepted": 1}


@pytest.mark.asyncio
async def test_benchmark_market_series_rejects_page_token_scope_mismatch() -> None:
    service = make_service()
    token = service._encode_page_token(  # pylint: disable=protected-access
        {"scope_fingerprint": "other-scope", "last_index_id": "IDX1"}
    )
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(return_value=[]),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
    )

    with pytest.raises(ValueError, match="page token does not match request scope"):
        await service.get_benchmark_market_series(
            benchmark_id="B1",
            request=SimpleNamespace(
                as_of_date=date(2026, 1, 1),
                window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
                frequency="daily",
                target_currency=None,
                series_fields=["index_price"],
                page=SimpleNamespace(page_size=2, page_token=token),
            ),
        )


@pytest.mark.asyncio
async def test_portfolio_tax_lot_window_returns_paged_portfolio_lots() -> None:
    service = make_service()
    service._buy_state_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_portfolio_tax_lots=AsyncMock(
            return_value=[
                (
                    SimpleNamespace(
                        portfolio_id="PB_SG_GLOBAL_BAL_001",
                        security_id="EQ_US_AAPL",
                        instrument_id="EQ_US_AAPL",
                        lot_id="LOT-AAPL-001",
                        open_quantity=Decimal("100.0000000000"),
                        original_quantity=Decimal("100.0000000000"),
                        acquisition_date=date(2026, 3, 25),
                        lot_cost_base=Decimal("15005.5000000000"),
                        lot_cost_local=Decimal("15005.5000000000"),
                        source_transaction_id="TXN-BUY-AAPL-001",
                        source_system="front_office_portfolio_seed",
                        calculation_policy_id="BUY_DEFAULT_POLICY",
                        calculation_policy_version="1.0.0",
                        updated_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
                    ),
                    "USD",
                ),
                (
                    SimpleNamespace(
                        portfolio_id="PB_SG_GLOBAL_BAL_001",
                        security_id="FI_US_TREASURY_10Y",
                        instrument_id="FI_US_TREASURY_10Y",
                        lot_id="LOT-UST-001",
                        open_quantity=Decimal("200.0000000000"),
                        original_quantity=Decimal("200.0000000000"),
                        acquisition_date=date(2026, 3, 26),
                        lot_cost_base=Decimal("20000.0000000000"),
                        lot_cost_local=Decimal("20000.0000000000"),
                        source_transaction_id="TXN-BUY-UST-001",
                        source_system="front_office_portfolio_seed",
                        calculation_policy_id="BUY_DEFAULT_POLICY",
                        calculation_policy_version="1.0.0",
                        updated_at=datetime(2026, 4, 10, 10, tzinfo=UTC),
                    ),
                    "USD",
                ),
            ]
        ),
    )

    response = await service.get_portfolio_tax_lot_window(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=PortfolioTaxLotWindowRequest(
            as_of_date=date(2026, 4, 10),
            security_ids=["EQ_US_AAPL"],
            page={"page_size": 1},
        ),
    )

    assert [lot.lot_id for lot in response.lots] == ["LOT-AAPL-001"]
    assert response.lots[0].local_currency == "USD"
    assert response.lots[0].tax_lot_status == "OPEN"
    assert response.lots[0].source_lineage["calculation_policy_id"] == "BUY_DEFAULT_POLICY"
    assert response.page.next_page_token is not None
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "TAX_LOTS_PAGE_PARTIAL"
    service._buy_state_repository.list_portfolio_tax_lots.assert_awaited_once_with(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=date(2026, 4, 10),
        security_ids=["EQ_US_AAPL"],
        include_closed_lots=False,
        lot_status_filter=None,
        after_sort_key=None,
        limit=2,
    )


@pytest.mark.asyncio
async def test_portfolio_tax_lot_window_reports_missing_requested_security() -> None:
    service = make_service()
    service._buy_state_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_portfolio_tax_lots=AsyncMock(return_value=[]),
    )

    response = await service.get_portfolio_tax_lot_window(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=PortfolioTaxLotWindowRequest(
            as_of_date=date(2026, 4, 10),
            security_ids=["UNKNOWN_SEC"],
        ),
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES"
    assert response.supportability.missing_security_ids == ["UNKNOWN_SEC"]
    assert response.data_quality_status == "PARTIAL"


@pytest.mark.asyncio
async def test_portfolio_tax_lot_window_marks_empty_full_portfolio_unavailable() -> None:
    service = make_service()
    service._buy_state_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_portfolio_tax_lots=AsyncMock(return_value=[]),
    )

    response = await service.get_portfolio_tax_lot_window(
        portfolio_id="PB_EMPTY",
        request=PortfolioTaxLotWindowRequest(as_of_date=date(2026, 4, 10)),
    )

    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "TAX_LOTS_EMPTY"
    assert response.supportability.returned_lot_count == 0
    assert response.supportability.missing_security_ids == []
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_portfolio_tax_lot_window_rejects_page_token_scope_mismatch() -> None:
    service = make_service()
    service._buy_state_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_portfolio_tax_lots=AsyncMock(return_value=[]),
    )
    token = service._encode_page_token(  # pylint: disable=protected-access
        {"scope_fingerprint": "other-scope", "last_lot_id": "LOT-AAPL-001"}
    )

    with pytest.raises(ValueError, match="page token does not match request scope"):
        await service.get_portfolio_tax_lot_window(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=PortfolioTaxLotWindowRequest(
                as_of_date=date(2026, 4, 10),
                page={"page_token": token},
            ),
        )


@pytest.mark.asyncio
async def test_transaction_cost_curve_returns_ready_observed_fee_evidence() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_transaction_cost_evidence=AsyncMock(
            return_value=[
                transaction_cost_row(
                    transaction_id="TXN-AAPL-001",
                    security_id="EQ_US_AAPL",
                    gross_transaction_amount=Decimal("10000.00"),
                    trade_fee=Decimal("999.99"),
                    costs=[
                        SimpleNamespace(amount=Decimal("6.00")),
                        SimpleNamespace(amount=Decimal("4.00")),
                    ],
                ),
                transaction_cost_row(
                    transaction_id="TXN-AAPL-002",
                    security_id="EQ_US_AAPL",
                    gross_transaction_amount=Decimal("20000.00"),
                    trade_fee=Decimal("20.00"),
                    transaction_date=datetime(2026, 4, 2, 10, tzinfo=UTC),
                ),
            ]
        ),
    )

    response = await service.get_transaction_cost_curve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
            security_ids=["EQ_US_AAPL"],
            transaction_types=["buy"],
            min_observation_count=2,
        ),
    )

    assert response.product_name == "TransactionCostCurve"
    assert response.supportability.state == "READY"
    assert response.data_quality_status == COMPLETE
    assert response.latest_evidence_timestamp == datetime(2026, 4, 2, 10, tzinfo=UTC)
    assert len(response.curve_points) == 1
    point = response.curve_points[0]
    assert point.security_id == "EQ_US_AAPL"
    assert point.transaction_type == "BUY"
    assert point.observation_count == 2
    assert point.total_cost == Decimal("30.00")
    assert point.total_notional == Decimal("30000.00")
    assert point.average_cost_bps == Decimal("10.0000")
    assert point.min_cost_bps == Decimal("10.0000")
    assert point.max_cost_bps == Decimal("10.0000")
    assert point.sample_transaction_ids == ["TXN-AAPL-001", "TXN-AAPL-002"]
    assert point.source_lineage["source_table"] == "transactions,transaction_costs"
    service._transaction_repository.list_transaction_cost_evidence.assert_awaited_once_with(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        security_ids=["EQ_US_AAPL"],
        transaction_types=["BUY"],
    )


@pytest.mark.asyncio
async def test_transaction_cost_curve_groups_by_security_type_and_currency() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_transaction_cost_evidence=AsyncMock(
            return_value=[
                transaction_cost_row(
                    transaction_id="TXN-AAPL-BUY-USD-001",
                    security_id="EQ_US_AAPL",
                    transaction_type="BUY",
                    currency="USD",
                    gross_transaction_amount=Decimal("10000.00"),
                    trade_fee=Decimal("10.00"),
                ),
                transaction_cost_row(
                    transaction_id="TXN-AAPL-BUY-USD-002",
                    security_id="EQ_US_AAPL",
                    transaction_type="BUY",
                    currency="USD",
                    gross_transaction_amount=Decimal("20000.00"),
                    trade_fee=Decimal("30.00"),
                ),
                transaction_cost_row(
                    transaction_id="TXN-AAPL-SELL-USD-001",
                    security_id="EQ_US_AAPL",
                    transaction_type="SELL",
                    currency="USD",
                    gross_transaction_amount=Decimal("15000.00"),
                    trade_fee=Decimal("15.00"),
                ),
                transaction_cost_row(
                    transaction_id="TXN-AAPL-BUY-SGD-001",
                    security_id="EQ_US_AAPL",
                    transaction_type="BUY",
                    currency="SGD",
                    gross_transaction_amount=Decimal("12000.00"),
                    trade_fee=Decimal("24.00"),
                ),
            ]
        ),
    )

    response = await service.get_transaction_cost_curve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
        ),
    )

    points = {
        (point.security_id, point.transaction_type, point.currency): point
        for point in response.curve_points
    }

    assert sorted(points) == [
        ("EQ_US_AAPL", "BUY", "SGD"),
        ("EQ_US_AAPL", "BUY", "USD"),
        ("EQ_US_AAPL", "SELL", "USD"),
    ]
    assert points[("EQ_US_AAPL", "BUY", "USD")].observation_count == 2
    assert points[("EQ_US_AAPL", "BUY", "USD")].average_cost_bps == Decimal("13.3333")
    assert points[("EQ_US_AAPL", "BUY", "USD")].min_cost_bps == Decimal("10.0000")
    assert points[("EQ_US_AAPL", "BUY", "USD")].max_cost_bps == Decimal("15.0000")
    assert points[("EQ_US_AAPL", "BUY", "SGD")].average_cost_bps == Decimal("20.0000")
    assert points[("EQ_US_AAPL", "SELL", "USD")].average_cost_bps == Decimal("10.0000")


@pytest.mark.asyncio
async def test_transaction_cost_curve_rejects_unknown_portfolio() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=False),
        list_transaction_cost_evidence=AsyncMock(),
    )

    with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
        await service.get_transaction_cost_curve(
            portfolio_id="P404",
            request=TransactionCostCurveRequest(
                as_of_date=date(2026, 5, 3),
                window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
            ),
        )

    service._transaction_repository.list_transaction_cost_evidence.assert_not_called()


@pytest.mark.asyncio
async def test_transaction_cost_curve_filters_unusable_and_insufficient_evidence() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_transaction_cost_evidence=AsyncMock(
            return_value=[
                transaction_cost_row(
                    transaction_id="TXN-NOFEE-001",
                    security_id="EQ_US_AAPL",
                    trade_fee=None,
                    costs=[],
                ),
                transaction_cost_row(
                    transaction_id="TXN-ZERO-001",
                    security_id="EQ_US_MSFT",
                    gross_transaction_amount=Decimal("0.00"),
                    trade_fee=Decimal("10.00"),
                ),
                transaction_cost_row(
                    transaction_id="TXN-SINGLE-001",
                    security_id="EQ_US_NVDA",
                    trade_fee=Decimal("10.00"),
                ),
            ]
        ),
    )

    response = await service.get_transaction_cost_curve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
            min_observation_count=2,
        ),
    )

    assert response.curve_points == []
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "TRANSACTION_COST_EVIDENCE_NOT_FOUND"
    assert response.data_quality_status == PARTIAL


@pytest.mark.asyncio
async def test_transaction_cost_curve_reports_incomplete_requested_security_coverage() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_transaction_cost_evidence=AsyncMock(
            return_value=[
                transaction_cost_row(
                    transaction_id="TXN-AAPL-001",
                    security_id="EQ_US_AAPL",
                    trade_fee=Decimal("10.00"),
                )
            ]
        ),
    )

    response = await service.get_transaction_cost_curve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
            security_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
        ),
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "TRANSACTION_COST_EVIDENCE_MISSING_FOR_SECURITIES"
    assert response.supportability.missing_security_ids == ["EQ_US_MSFT"]
    assert response.data_quality_status == PARTIAL


@pytest.mark.asyncio
async def test_transaction_cost_curve_pages_observed_points_deterministically() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_transaction_cost_evidence=AsyncMock(
            return_value=[
                transaction_cost_row(transaction_id="TXN-AAPL-001", security_id="EQ_US_AAPL"),
                transaction_cost_row(transaction_id="TXN-MSFT-001", security_id="EQ_US_MSFT"),
            ]
        ),
    )

    first_page = await service.get_transaction_cost_curve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
            page={"page_size": 1},
        ),
    )

    assert [point.security_id for point in first_page.curve_points] == ["EQ_US_AAPL"]
    assert first_page.supportability.state == "DEGRADED"
    assert first_page.supportability.reason == "TRANSACTION_COST_CURVE_PAGE_PARTIAL"
    assert first_page.page.next_page_token is not None

    second_page = await service.get_transaction_cost_curve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
            page={"page_size": 1, "page_token": first_page.page.next_page_token},
        ),
    )

    assert [point.security_id for point in second_page.curve_points] == ["EQ_US_MSFT"]
    assert second_page.page.next_page_token is None


@pytest.mark.asyncio
async def test_transaction_cost_curve_reports_missing_requested_security() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_transaction_cost_evidence=AsyncMock(return_value=[]),
    )

    response = await service.get_transaction_cost_curve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
            security_ids=["EQ_US_AAPL"],
        ),
    )

    assert response.curve_points == []
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "TRANSACTION_COST_EVIDENCE_NOT_FOUND"
    assert response.supportability.missing_security_ids == ["EQ_US_AAPL"]
    assert response.data_quality_status == PARTIAL


@pytest.mark.asyncio
async def test_transaction_cost_curve_rejects_page_token_scope_mismatch() -> None:
    service = make_service()
    service._transaction_repository = SimpleNamespace(  # type: ignore[assignment]
        portfolio_exists=AsyncMock(return_value=True),
        list_transaction_cost_evidence=AsyncMock(return_value=[]),
    )
    token = service._encode_page_token(  # pylint: disable=protected-access
        {"scope_fingerprint": "different-curve-scope", "last_curve_key": ["A", "BUY", "USD"]}
    )

    with pytest.raises(ValueError, match="page token does not match request scope"):
        await service.get_transaction_cost_curve(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=TransactionCostCurveRequest(
                as_of_date=date(2026, 5, 3),
                window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)},
                page={"page_token": token},
            ),
        )


@pytest.mark.asyncio
async def test_market_data_coverage_returns_price_and_fx_supportability() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        list_latest_market_prices=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="EQ_US_AAPL",
                    price_date=date(2026, 4, 10),
                    price=Decimal("187.1200000000"),
                    currency="USD",
                    updated_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
                ),
                SimpleNamespace(
                    security_id="FI_US_TREASURY_10Y",
                    price_date=date(2026, 4, 1),
                    price=Decimal("98.5000000000"),
                    currency="USD",
                    updated_at=datetime(2026, 4, 1, 9, tzinfo=UTC),
                ),
            ]
        ),
        list_latest_fx_rates=AsyncMock(
            return_value=[
                SimpleNamespace(
                    from_currency="USD",
                    to_currency="SGD",
                    rate_date=date(2026, 4, 10),
                    rate=Decimal("1.3521000000"),
                    updated_at=datetime(2026, 4, 10, 10, tzinfo=UTC),
                )
            ]
        ),
    )

    response = await service.get_market_data_coverage(
        MarketDataCoverageRequest(
            as_of_date=date(2026, 4, 10),
            instrument_ids=["EQ_US_AAPL", "FI_US_TREASURY_10Y", "UNKNOWN_SEC"],
            currency_pairs=[{"from_currency": "USD", "to_currency": "SGD"}],
            valuation_currency="SGD",
            max_staleness_days=5,
            tenant_id="tenant_sg_pb",
        )
    )

    assert response.product_name == "MarketDataCoverageWindow"
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MARKET_DATA_MISSING"
    assert response.supportability.missing_instrument_ids == ["UNKNOWN_SEC"]
    assert response.supportability.stale_instrument_ids == ["FI_US_TREASURY_10Y"]
    assert response.price_coverage[0].quality_status == "READY"
    assert response.price_coverage[1].quality_status == "STALE"
    assert response.fx_coverage[0].rate == Decimal("1.3521000000")
    assert response.data_quality_status == "PARTIAL"
    service._reference_repository.list_latest_market_prices.assert_awaited_once_with(
        security_ids=["EQ_US_AAPL", "FI_US_TREASURY_10Y", "UNKNOWN_SEC"],
        as_of_date=date(2026, 4, 10),
    )
    service._reference_repository.list_latest_fx_rates.assert_awaited_once_with(
        currency_pairs=[("USD", "SGD")],
        as_of_date=date(2026, 4, 10),
    )


@pytest.mark.asyncio
async def test_market_data_coverage_reports_stale_without_missing_as_degraded() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        list_latest_market_prices=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="EQ_US_AAPL",
                    price_date=date(2026, 4, 1),
                    price=Decimal("187.1200000000"),
                    currency="USD",
                )
            ]
        ),
        list_latest_fx_rates=AsyncMock(return_value=[]),
    )

    response = await service.get_market_data_coverage(
        MarketDataCoverageRequest(
            as_of_date=date(2026, 4, 10),
            instrument_ids=["EQ_US_AAPL"],
            max_staleness_days=5,
        )
    )

    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MARKET_DATA_STALE"
    assert response.supportability.stale_instrument_ids == ["EQ_US_AAPL"]
    assert response.supportability.missing_instrument_ids == []


@pytest.mark.asyncio
async def test_dpm_source_readiness_returns_ready_when_all_families_ready() -> None:
    service = make_service()
    service.resolve_discretionary_mandate_binding = AsyncMock(
        return_value=SimpleNamespace(
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            supportability=SimpleNamespace(
                state="READY",
                reason="MANDATE_BINDING_READY",
                missing_data_families=[],
            ),
        )
    )
    service.resolve_model_portfolio_targets = AsyncMock(
        return_value=SimpleNamespace(
            targets=[
                SimpleNamespace(instrument_id="FO_EQ_AAPL_US"),
                SimpleNamespace(instrument_id="FO_BOND_UST_2030"),
            ],
            supportability=SimpleNamespace(
                state="READY",
                reason="MODEL_TARGETS_READY",
                target_count=2,
            ),
        )
    )
    service.resolve_instrument_eligibility_bulk = AsyncMock(
        return_value=SimpleNamespace(
            supportability=SimpleNamespace(
                state="READY",
                reason="INSTRUMENT_ELIGIBILITY_READY",
                missing_security_ids=[],
                resolved_count=2,
            )
        )
    )
    service.get_portfolio_tax_lot_window = AsyncMock(
        return_value=SimpleNamespace(
            supportability=SimpleNamespace(
                state="READY",
                reason="TAX_LOTS_READY",
                missing_security_ids=[],
                returned_lot_count=2,
            )
        )
    )
    service.get_market_data_coverage = AsyncMock(
        return_value=SimpleNamespace(
            supportability=SimpleNamespace(
                state="READY",
                reason="MARKET_DATA_READY",
                missing_instrument_ids=[],
                missing_currency_pairs=[],
                stale_instrument_ids=[],
                stale_currency_pairs=[],
                resolved_price_count=2,
                resolved_fx_count=1,
            )
        )
    )

    response = await service.get_dpm_source_readiness(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=DpmSourceReadinessRequest(
            as_of_date=date(2026, 4, 10),
            tenant_id="tenant_sg_pb",
            currency_pairs=[{"from_currency": "EUR", "to_currency": "USD"}],
            valuation_currency="USD",
        ),
    )

    assert response.product_name == "DpmSourceReadiness"
    assert response.supportability.state == "READY"
    assert response.supportability.ready_family_count == 5
    assert response.evaluated_instrument_ids == ["FO_BOND_UST_2030", "FO_EQ_AAPL_US"]
    assert [family.family for family in response.families] == [
        "mandate",
        "model_targets",
        "eligibility",
        "tax_lots",
        "market_data",
    ]


@pytest.mark.asyncio
async def test_dpm_source_readiness_blocks_when_key_families_unavailable() -> None:
    service = make_service()
    service.resolve_discretionary_mandate_binding = AsyncMock(return_value=None)
    service.resolve_instrument_eligibility_bulk = AsyncMock(
        return_value=SimpleNamespace(
            supportability=SimpleNamespace(
                state="READY",
                reason="INSTRUMENT_ELIGIBILITY_READY",
                missing_security_ids=[],
                resolved_count=1,
            )
        )
    )
    service.get_portfolio_tax_lot_window = AsyncMock(side_effect=LookupError("missing"))
    service.get_market_data_coverage = AsyncMock(
        return_value=SimpleNamespace(
            supportability=SimpleNamespace(
                state="INCOMPLETE",
                reason="MARKET_DATA_MISSING",
                missing_instrument_ids=["FO_EQ_AAPL_US"],
                missing_currency_pairs=[],
                stale_instrument_ids=[],
                stale_currency_pairs=[],
                resolved_price_count=0,
                resolved_fx_count=0,
            )
        )
    )

    response = await service.get_dpm_source_readiness(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=DpmSourceReadinessRequest(
            as_of_date=date(2026, 4, 10),
            instrument_ids=["FO_EQ_AAPL_US"],
        ),
    )

    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.unavailable_family_count == 3
    assert response.supportability.incomplete_family_count == 1
    reasons = {family.family: family.reason for family in response.families}
    assert reasons["mandate"] == "MANDATE_BINDING_UNAVAILABLE"
    assert reasons["model_targets"] == "MODEL_PORTFOLIO_ID_UNAVAILABLE"
    assert reasons["tax_lots"] == "PORTFOLIO_TAX_LOTS_UNAVAILABLE"


@pytest.mark.asyncio
async def test_dpm_source_readiness_degrades_source_family_exceptions() -> None:
    service = make_service()
    service.resolve_discretionary_mandate_binding = AsyncMock(
        return_value=SimpleNamespace(
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            supportability=SimpleNamespace(
                state="READY",
                reason="MANDATE_BINDING_READY",
                missing_data_families=[],
            ),
        )
    )
    service.resolve_model_portfolio_targets = AsyncMock(
        side_effect=ValueError("model source unavailable")
    )
    service.resolve_instrument_eligibility_bulk = AsyncMock(
        side_effect=ValueError("eligibility source unavailable")
    )
    service.get_portfolio_tax_lot_window = AsyncMock(
        side_effect=ValueError("tax lot source unavailable")
    )
    service.get_market_data_coverage = AsyncMock(
        side_effect=ValueError("market source unavailable")
    )

    response = await service.get_dpm_source_readiness(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=DpmSourceReadinessRequest(
            as_of_date=date(2026, 4, 10),
            instrument_ids=["FO_EQ_AAPL_US"],
        ),
    )

    assert response.supportability.state == "UNAVAILABLE"
    reasons = {family.family: family.reason for family in response.families}
    assert reasons == {
        "mandate": "MANDATE_BINDING_READY",
        "model_targets": "MODEL_TARGETS_UNAVAILABLE",
        "eligibility": "INSTRUMENT_ELIGIBILITY_UNAVAILABLE",
        "tax_lots": "PORTFOLIO_TAX_LOTS_UNAVAILABLE",
        "market_data": "MARKET_DATA_COVERAGE_UNAVAILABLE",
    }


@pytest.mark.asyncio
async def test_benchmark_market_series_honors_window_rebalances() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    composition_weight=Decimal("0.60"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=date(2026, 1, 1),
                ),
                SimpleNamespace(
                    index_id="IDX_A",
                    composition_weight=Decimal("0.55"),
                    composition_effective_from=date(2026, 1, 2),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX_B",
                    composition_weight=Decimal("0.40"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=date(2026, 1, 1),
                ),
                SimpleNamespace(
                    index_id="IDX_C",
                    composition_weight=Decimal("0.45"),
                    composition_effective_from=date(2026, 1, 2),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 2),
                    index_price=Decimal("101"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    index_id="IDX_B",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("200"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    index_id="IDX_C",
                    series_date=date(2026, 1, 2),
                    index_price=Decimal("300"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    benchmark_return=Decimal("0.01"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    series_date=date(2026, 1, 2),
                    benchmark_return=Decimal("0.02"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        get_fx_rates=AsyncMock(return_value={}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 2),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price", "component_weight", "benchmark_return"],
            page=SimpleNamespace(page_size=10, page_token=None),
        ),
    )

    assert [row.index_id for row in response.component_series] == ["IDX_A", "IDX_B", "IDX_C"]
    idx_a_points = next(row.points for row in response.component_series if row.index_id == "IDX_A")
    idx_b_points = next(row.points for row in response.component_series if row.index_id == "IDX_B")
    idx_c_points = next(row.points for row in response.component_series if row.index_id == "IDX_C")
    assert [point.component_weight for point in idx_a_points] == [
        Decimal("0.60"),
        Decimal("0.55"),
    ]
    assert [point.component_weight for point in idx_b_points] == [Decimal("0.40"), None]
    assert [point.component_weight for point in idx_c_points] == [None, Decimal("0.45")]


@pytest.mark.asyncio
async def test_benchmark_market_series_honors_requested_series_fields() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    composition_weight=Decimal("0.60"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        list_index_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 1),
                    index_return=Decimal("0.01"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        list_benchmark_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    benchmark_return=Decimal("0.02"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        get_fx_rates=AsyncMock(return_value={date(2026, 1, 1): Decimal("1.10")}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)),
            frequency="daily",
            target_currency="EUR",
            series_fields=["benchmark_return", "component_weight"],
            page=SimpleNamespace(page_size=10, page_token=None),
        ),
    )

    point = response.component_series[0].points[0]
    assert point.index_price is None
    assert point.index_return is None
    assert point.benchmark_return == Decimal("0.02")
    assert point.component_weight == Decimal("0.60")
    assert point.fx_rate is None
