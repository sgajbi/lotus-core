import pytest
from portfolio_common.source_data_products import SOURCE_DATA_PRODUCT_CATALOG
from portfolio_common.source_data_security import (
    AUDIT_OPERATOR_ACCESS,
    AUDIT_SYSTEM_ACCESS,
    CLIENT_CONFIDENTIAL,
    OPERATOR_ACCESS,
    RETAIN_FOR_OPERATIONAL_AUDIT,
    SYSTEM_ACCESS,
    SOURCE_DATA_SECURITY_PROFILES,
    SourceDataSecurityProfile,
    get_source_data_security_profile,
    validate_source_data_security_profiles,
)


def test_source_data_security_profiles_cover_product_catalog() -> None:
    validate_source_data_security_profiles()


def test_every_source_data_product_has_tenant_and_entitlement_profile() -> None:
    for product in SOURCE_DATA_PRODUCT_CATALOG:
        profile = get_source_data_security_profile(product.product_name)

        assert profile.tenant_required is True
        assert profile.entitlement_required is True


def test_client_source_products_classify_sensitive_identifiers() -> None:
    profile = get_source_data_security_profile("TransactionLedgerWindow")

    assert profile.sensitivity_classification == "client_sensitive"
    assert {"portfolio_id", "client_id", "transaction_id"} <= set(profile.pii_fields)


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
