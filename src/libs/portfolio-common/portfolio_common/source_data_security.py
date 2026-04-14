"""RFC-0083 source-data product security and lifecycle profile helpers."""

from __future__ import annotations

from dataclasses import dataclass

from portfolio_common.source_data_products import SOURCE_DATA_PRODUCT_CATALOG


CLIENT_CONFIDENTIAL = "client_confidential"
CLIENT_SENSITIVE = "client_sensitive"
INTERNAL_OPERATIONAL = "internal_operational"
REFERENCE_INTERNAL = "reference_internal"

BUSINESS_CONSUMER_ACCESS = "business_consumer_access"
OPERATOR_ACCESS = "operator_access"
SYSTEM_ACCESS = "system_access"

RETAIN_FOR_CLIENT_RECORD = "retain_for_client_record"
RETAIN_FOR_SOURCE_AUDIT = "retain_for_source_audit"
RETAIN_FOR_OPERATIONAL_AUDIT = "retain_for_operational_audit"

AUDIT_READ_AND_EXPORT = "audit_read_and_export"
AUDIT_OPERATOR_ACCESS = "audit_operator_access"
AUDIT_SYSTEM_ACCESS = "audit_system_access"


@dataclass(frozen=True)
class SourceDataSecurityProfile:
    product_name: str
    tenant_required: bool
    entitlement_required: bool
    access_classification: str
    sensitivity_classification: str
    retention_requirement: str
    audit_requirement: str
    pii_fields: tuple[str, ...] = ()
    operator_only: bool = False


SOURCE_DATA_SECURITY_PROFILES: tuple[SourceDataSecurityProfile, ...] = (
    SourceDataSecurityProfile(
        product_name="PortfolioStateSnapshot",
        tenant_required=True,
        entitlement_required=True,
        access_classification=BUSINESS_CONSUMER_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_READ_AND_EXPORT,
        pii_fields=("portfolio_id", "client_id"),
    ),
    SourceDataSecurityProfile(
        product_name="HoldingsAsOf",
        tenant_required=True,
        entitlement_required=True,
        access_classification=BUSINESS_CONSUMER_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_READ_AND_EXPORT,
        pii_fields=("portfolio_id", "client_id"),
    ),
    SourceDataSecurityProfile(
        product_name="TransactionLedgerWindow",
        tenant_required=True,
        entitlement_required=True,
        access_classification=BUSINESS_CONSUMER_ACCESS,
        sensitivity_classification=CLIENT_SENSITIVE,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_READ_AND_EXPORT,
        pii_fields=("portfolio_id", "client_id", "transaction_id"),
    ),
    SourceDataSecurityProfile(
        product_name="PositionTimeseriesInput",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
        pii_fields=("portfolio_id",),
    ),
    SourceDataSecurityProfile(
        product_name="PortfolioTimeseriesInput",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
        pii_fields=("portfolio_id",),
    ),
    SourceDataSecurityProfile(
        product_name="MarketDataWindow",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
    ),
    SourceDataSecurityProfile(
        product_name="InstrumentReferenceBundle",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
    ),
    SourceDataSecurityProfile(
        product_name="BenchmarkAssignment",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
        pii_fields=("portfolio_id",),
    ),
    SourceDataSecurityProfile(
        product_name="BenchmarkConstituentWindow",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
    ),
    SourceDataSecurityProfile(
        product_name="IndexSeriesWindow",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
    ),
    SourceDataSecurityProfile(
        product_name="RiskFreeSeriesWindow",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
    ),
    SourceDataSecurityProfile(
        product_name="ReconciliationEvidenceBundle",
        tenant_required=True,
        entitlement_required=True,
        access_classification=OPERATOR_ACCESS,
        sensitivity_classification=INTERNAL_OPERATIONAL,
        retention_requirement=RETAIN_FOR_OPERATIONAL_AUDIT,
        audit_requirement=AUDIT_OPERATOR_ACCESS,
        pii_fields=("portfolio_id", "transaction_id"),
        operator_only=True,
    ),
    SourceDataSecurityProfile(
        product_name="DataQualityCoverageReport",
        tenant_required=True,
        entitlement_required=True,
        access_classification=OPERATOR_ACCESS,
        sensitivity_classification=INTERNAL_OPERATIONAL,
        retention_requirement=RETAIN_FOR_OPERATIONAL_AUDIT,
        audit_requirement=AUDIT_OPERATOR_ACCESS,
        pii_fields=("portfolio_id",),
        operator_only=True,
    ),
    SourceDataSecurityProfile(
        product_name="IngestionEvidenceBundle",
        tenant_required=True,
        entitlement_required=True,
        access_classification=OPERATOR_ACCESS,
        sensitivity_classification=INTERNAL_OPERATIONAL,
        retention_requirement=RETAIN_FOR_OPERATIONAL_AUDIT,
        audit_requirement=AUDIT_OPERATOR_ACCESS,
        pii_fields=("portfolio_id", "source_record_id", "source_batch_id"),
        operator_only=True,
    ),
)


def get_source_data_security_profile(product_name: str) -> SourceDataSecurityProfile:
    requested = _normalize_required_text(product_name, "product_name")
    for profile in SOURCE_DATA_SECURITY_PROFILES:
        if profile.product_name.upper() == requested:
            return profile
    raise KeyError(f"Unknown source-data security profile: {product_name}")


def validate_source_data_security_profiles(
    profiles: tuple[SourceDataSecurityProfile, ...] = SOURCE_DATA_SECURITY_PROFILES,
) -> None:
    catalog_product_names = {
        product.product_name.upper(): product.product_name
        for product in SOURCE_DATA_PRODUCT_CATALOG
    }
    profile_product_names: dict[str, str] = {}
    profile_names: set[str] = set()
    for profile in profiles:
        product_name = _normalize_required_text(profile.product_name, "product_name")
        if product_name in profile_names:
            raise ValueError(f"Duplicate source-data security profile: {profile.product_name}")
        profile_names.add(product_name)
        profile_product_names[product_name] = profile.product_name
        _require_allowed(
            profile.access_classification,
            "access_classification",
            {BUSINESS_CONSUMER_ACCESS, OPERATOR_ACCESS, SYSTEM_ACCESS},
        )
        _require_allowed(
            profile.sensitivity_classification,
            "sensitivity_classification",
            {
                CLIENT_CONFIDENTIAL,
                CLIENT_SENSITIVE,
                INTERNAL_OPERATIONAL,
                REFERENCE_INTERNAL,
            },
        )
        _require_allowed(
            profile.retention_requirement,
            "retention_requirement",
            {
                RETAIN_FOR_CLIENT_RECORD,
                RETAIN_FOR_SOURCE_AUDIT,
                RETAIN_FOR_OPERATIONAL_AUDIT,
            },
        )
        _require_allowed(
            profile.audit_requirement,
            "audit_requirement",
            {AUDIT_READ_AND_EXPORT, AUDIT_OPERATOR_ACCESS, AUDIT_SYSTEM_ACCESS},
        )
        if not profile.tenant_required:
            raise ValueError(f"{profile.product_name} must require tenant scoping")
        if not profile.entitlement_required:
            raise ValueError(f"{profile.product_name} must require entitlement scoping")
        if profile.operator_only and profile.access_classification != OPERATOR_ACCESS:
            raise ValueError(f"{profile.product_name} operator_only requires operator access")
        if (
            profile.sensitivity_classification in {CLIENT_CONFIDENTIAL, CLIENT_SENSITIVE}
            and not profile.pii_fields
        ):
            raise ValueError(f"{profile.product_name} requires pii_fields for client sensitivity")
        for pii_field in profile.pii_fields:
            _normalize_required_text(pii_field, "pii_fields")

    normalized_product_names = set(catalog_product_names)
    missing_profiles = [
        catalog_product_names[name] for name in sorted(normalized_product_names - profile_names)
    ]
    extra_profiles = [
        profile_product_names[name] for name in sorted(profile_names - normalized_product_names)
    ]
    if missing_profiles:
        raise ValueError("Missing source-data security profile(s): " + ", ".join(missing_profiles))
    if extra_profiles:
        raise ValueError("Unknown source-data security profile(s): " + ", ".join(extra_profiles))


def _require_allowed(value: str, field_name: str, allowed: set[str]) -> None:
    normalized = _normalize_required_text(value, field_name)
    if normalized not in {item.upper() for item in allowed}:
        raise ValueError(f"{field_name} has unsupported value: {value}")


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized
