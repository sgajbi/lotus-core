import pytest
from portfolio_common.source_data_products import SOURCE_DATA_PRODUCT_CATALOG
from portfolio_common.source_data_security import (
    AUDIT_OPERATOR_ACCESS,
    AUDIT_SYSTEM_ACCESS,
    CLIENT_CONFIDENTIAL,
    CLIENT_SENSITIVE,
    DPM_PLANNED_SOURCE_DATA_SECURITY_PROFILES,
    OPERATOR_ACCESS,
    RETAIN_FOR_OPERATIONAL_AUDIT,
    SYSTEM_ACCESS,
    SOURCE_DATA_SECURITY_PROFILES,
    SourceDataSecurityProfile,
    get_source_data_security_profile,
    required_source_data_capability,
    source_data_capability_rules,
    source_data_security_openapi_extra,
    validate_dpm_planned_source_data_security_profiles,
    validate_source_data_security_profiles,
)


def test_source_data_security_profiles_cover_product_catalog() -> None:
    validate_source_data_security_profiles()


def test_dpm_planned_source_data_security_profiles_cover_planned_catalog() -> None:
    validate_dpm_planned_source_data_security_profiles()


def test_dpm_planned_source_data_security_profiles_are_system_scoped() -> None:
    expected_profiles = {
        "MarketDataCoverageWindow",
    }
    profiles = {
        profile.product_name: profile for profile in DPM_PLANNED_SOURCE_DATA_SECURITY_PROFILES
    }

    assert set(profiles) == expected_profiles
    for profile in profiles.values():
        assert profile.access_classification == SYSTEM_ACCESS
        assert profile.audit_requirement == AUDIT_SYSTEM_ACCESS
        assert profile.operator_only is False


def test_every_source_data_product_has_tenant_and_entitlement_profile() -> None:
    for product in SOURCE_DATA_PRODUCT_CATALOG:
        profile = get_source_data_security_profile(product.product_name)

        assert profile.tenant_required is True
        assert profile.entitlement_required is True


def test_client_source_products_classify_sensitive_identifiers() -> None:
    profile = get_source_data_security_profile("TransactionLedgerWindow")

    assert profile.sensitivity_classification == "client_sensitive"
    assert {"portfolio_id", "client_id", "transaction_id"} <= set(profile.pii_fields)
    tax_lot_profile = get_source_data_security_profile("PortfolioTaxLotWindow")
    assert tax_lot_profile.sensitivity_classification == CLIENT_SENSITIVE
    assert {"portfolio_id", "lot_id", "source_transaction_id"} <= set(tax_lot_profile.pii_fields)


def test_operator_evidence_products_require_operator_access_and_operational_retention() -> None:
    for product_name in (
        "ReconciliationEvidenceBundle",
        "DataQualityCoverageReport",
        "IngestionEvidenceBundle",
    ):
        profile = get_source_data_security_profile(product_name)

        assert profile.operator_only is True
        assert profile.access_classification == OPERATOR_ACCESS
        assert profile.retention_requirement == RETAIN_FOR_OPERATIONAL_AUDIT
        assert profile.audit_requirement == AUDIT_OPERATOR_ACCESS


def test_analytics_input_products_require_system_access_classification() -> None:
    for product_name in (
        "PositionTimeseriesInput",
        "PortfolioTimeseriesInput",
        "PortfolioAnalyticsReference",
        "MarketDataWindow",
        "InstrumentReferenceBundle",
        "BenchmarkAssignment",
        "BenchmarkConstituentWindow",
        "DpmModelPortfolioTarget",
        "DiscretionaryMandateBinding",
        "InstrumentEligibilityProfile",
        "PortfolioTaxLotWindow",
        "IndexSeriesWindow",
        "RiskFreeSeriesWindow",
    ):
        profile = get_source_data_security_profile(product_name)

        assert profile.access_classification == SYSTEM_ACCESS


def test_security_profiles_align_audit_requirement_to_access_classification() -> None:
    expected_audit_by_access = {
        "business_consumer_access": "audit_read_and_export",
        "system_access": "audit_system_access",
        "operator_access": "audit_operator_access",
    }

    for product in SOURCE_DATA_PRODUCT_CATALOG:
        profile = get_source_data_security_profile(product.product_name)

        assert profile.audit_requirement == expected_audit_by_access[profile.access_classification]


def test_security_profiles_align_retention_to_sensitivity_classification() -> None:
    expected_retention_by_sensitivity = {
        "client_confidential": "retain_for_client_record",
        "client_sensitive": "retain_for_client_record",
        "reference_internal": "retain_for_source_audit",
        "internal_operational": "retain_for_operational_audit",
    }

    for product in SOURCE_DATA_PRODUCT_CATALOG:
        profile = get_source_data_security_profile(product.product_name)

        assert (
            profile.retention_requirement
            == expected_retention_by_sensitivity[profile.sensitivity_classification]
        )


def test_portfolio_snapshot_profile_is_client_confidential() -> None:
    profile = get_source_data_security_profile("PortfolioStateSnapshot")

    assert profile.sensitivity_classification == CLIENT_CONFIDENTIAL
    assert {"portfolio_id", "client_id"} <= set(profile.pii_fields)


def test_portfolio_analytics_reference_profile_is_system_client_confidential() -> None:
    profile = get_source_data_security_profile("PortfolioAnalyticsReference")

    assert profile.access_classification == SYSTEM_ACCESS
    assert profile.sensitivity_classification == CLIENT_CONFIDENTIAL
    assert profile.audit_requirement == AUDIT_SYSTEM_ACCESS
    assert {"portfolio_id", "client_id"} <= set(profile.pii_fields)
    assert profile.operator_only is False


def test_discretionary_mandate_binding_profile_is_client_confidential_system_access() -> None:
    profile = get_source_data_security_profile("DiscretionaryMandateBinding")

    assert profile.access_classification == SYSTEM_ACCESS
    assert profile.sensitivity_classification == CLIENT_CONFIDENTIAL
    assert {"portfolio_id", "client_id"} <= set(profile.pii_fields)
    assert profile.audit_requirement == AUDIT_SYSTEM_ACCESS


def test_source_data_security_openapi_extra_exposes_governed_profile() -> None:
    extra = source_data_security_openapi_extra("PortfolioAnalyticsReference")

    extension = extra["x-lotus-source-data-security"]

    assert extension["product_name"] == "PortfolioAnalyticsReference"
    assert extension["tenant_required"] is True
    assert extension["entitlement_required"] is True
    assert extension["access_classification"] == SYSTEM_ACCESS
    assert extension["sensitivity_classification"] == CLIENT_CONFIDENTIAL
    assert extension["audit_requirement"] == AUDIT_SYSTEM_ACCESS
    assert extension["required_capability"] == "source_data.portfolio_analytics_reference.read"
    assert {"portfolio_id", "client_id"} <= set(extension["pii_fields"])
    assert extension["operator_only"] is False


def test_source_data_products_have_default_read_capability_rules() -> None:
    rules = source_data_capability_rules()

    assert (
        rules["POST /integration/portfolios/{portfolio_id}/analytics/reference"]
        == "source_data.portfolio_analytics_reference.read"
    )
    assert (
        rules["GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings"]
        == "source_data.reconciliation_evidence_bundle.read"
    )
    for product in SOURCE_DATA_PRODUCT_CATALOG:
        capability = required_source_data_capability(product.product_name)
        for route in product.current_routes:
            assert rules[f"GET {route}"] == capability
            assert rules[f"POST {route}"] == capability


def test_security_profile_validation_rejects_missing_product_profile() -> None:
    incomplete_profiles = tuple(
        profile
        for profile in SOURCE_DATA_SECURITY_PROFILES
        if profile.product_name != "HoldingsAsOf"
    )

    with pytest.raises(ValueError, match="HoldingsAsOf"):
        validate_source_data_security_profiles(incomplete_profiles)


def test_security_profile_validation_rejects_operator_only_without_operator_access() -> None:
    invalid = SourceDataSecurityProfile(
        product_name="PortfolioStateSnapshot",
        tenant_required=True,
        entitlement_required=True,
        access_classification="system_access",
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement="retain_for_client_record",
        audit_requirement="audit_system_access",
        operator_only=True,
    )

    with pytest.raises(ValueError, match="operator_only requires operator access"):
        validate_source_data_security_profiles((invalid,))


def test_security_profile_validation_rejects_operator_only_business_product() -> None:
    invalid = SourceDataSecurityProfile(
        product_name="PortfolioStateSnapshot",
        tenant_required=True,
        entitlement_required=True,
        access_classification=OPERATOR_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_OPERATIONAL_AUDIT,
        audit_requirement=AUDIT_OPERATOR_ACCESS,
        pii_fields=("portfolio_id", "client_id"),
        operator_only=True,
    )

    with pytest.raises(ValueError, match="operator_only requires control-plane route family"):
        validate_source_data_security_profiles((invalid,))


def test_security_profile_validation_rejects_operator_audit_without_operator_only() -> None:
    invalid = SourceDataSecurityProfile(
        product_name="PortfolioStateSnapshot",
        tenant_required=True,
        entitlement_required=True,
        access_classification=OPERATOR_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_OPERATIONAL_AUDIT,
        audit_requirement=AUDIT_OPERATOR_ACCESS,
        pii_fields=("portfolio_id", "client_id"),
        operator_only=False,
    )

    with pytest.raises(ValueError, match="operator audit requires operator_only"):
        validate_source_data_security_profiles((invalid,))


def test_security_profile_validation_rejects_access_classification_route_family_mismatch() -> None:
    invalid = SourceDataSecurityProfile(
        product_name="PortfolioTimeseriesInput",
        tenant_required=True,
        entitlement_required=True,
        access_classification="business_consumer_access",
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement="retain_for_client_record",
        audit_requirement="audit_read_and_export",
        pii_fields=("portfolio_id",),
    )

    with pytest.raises(ValueError, match="not valid for route family"):
        validate_source_data_security_profiles((invalid,))


def test_security_profile_validation_rejects_access_audit_mismatch() -> None:
    invalid = SourceDataSecurityProfile(
        product_name="PortfolioTimeseriesInput",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement="retain_for_client_record",
        audit_requirement="audit_read_and_export",
        pii_fields=("portfolio_id",),
    )

    with pytest.raises(ValueError, match="audit_requirement .* is not valid"):
        validate_source_data_security_profiles((invalid,))


def test_security_profile_validation_rejects_sensitivity_retention_mismatch() -> None:
    invalid = SourceDataSecurityProfile(
        product_name="PortfolioAnalyticsReference",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement="retain_for_source_audit",
        audit_requirement="audit_system_access",
        pii_fields=("portfolio_id", "client_id"),
    )

    with pytest.raises(ValueError, match="retention_requirement .* is not valid"):
        validate_source_data_security_profiles((invalid,))


def test_security_profile_validation_rejects_client_sensitivity_without_pii_fields() -> None:
    invalid = SourceDataSecurityProfile(
        product_name="PortfolioStateSnapshot",
        tenant_required=True,
        entitlement_required=True,
        access_classification="business_consumer_access",
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement="retain_for_client_record",
        audit_requirement="audit_read_and_export",
    )

    with pytest.raises(ValueError, match="requires pii_fields for client sensitivity"):
        validate_source_data_security_profiles((invalid,))
