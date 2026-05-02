"""RFC-0083 source-data product security and lifecycle profile helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from portfolio_common.source_data_products import (
    ANALYTICS_INPUT,
    CONTROL_PLANE_AND_POLICY,
    DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG,
    OPERATIONAL_READ,
    SOURCE_DATA_PRODUCT_CATALOG,
    SNAPSHOT_AND_SIMULATION,
    SourceDataProductDefinition,
)


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
SOURCE_DATA_READ_METHODS = ("GET", "POST")

ACCESS_CLASSIFICATION_ROUTE_FAMILIES = {
    BUSINESS_CONSUMER_ACCESS: {OPERATIONAL_READ, SNAPSHOT_AND_SIMULATION},
    SYSTEM_ACCESS: {ANALYTICS_INPUT},
    OPERATOR_ACCESS: {CONTROL_PLANE_AND_POLICY},
}
ACCESS_CLASSIFICATION_AUDIT_REQUIREMENT = {
    BUSINESS_CONSUMER_ACCESS: AUDIT_READ_AND_EXPORT,
    SYSTEM_ACCESS: AUDIT_SYSTEM_ACCESS,
    OPERATOR_ACCESS: AUDIT_OPERATOR_ACCESS,
}
SENSITIVITY_RETENTION_REQUIREMENT = {
    CLIENT_CONFIDENTIAL: RETAIN_FOR_CLIENT_RECORD,
    CLIENT_SENSITIVE: RETAIN_FOR_CLIENT_RECORD,
    REFERENCE_INTERNAL: RETAIN_FOR_SOURCE_AUDIT,
    INTERNAL_OPERATIONAL: RETAIN_FOR_OPERATIONAL_AUDIT,
}


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
        product_name="PortfolioAnalyticsReference",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
        pii_fields=("portfolio_id", "client_id"),
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
        product_name="DpmModelPortfolioTarget",
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

DPM_PLANNED_SOURCE_DATA_SECURITY_PROFILES: tuple[SourceDataSecurityProfile, ...] = (
    SourceDataSecurityProfile(
        product_name="DiscretionaryMandateBinding",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=CLIENT_CONFIDENTIAL,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
        pii_fields=("portfolio_id", "client_id"),
    ),
    SourceDataSecurityProfile(
        product_name="InstrumentEligibilityProfile",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
    ),
    SourceDataSecurityProfile(
        product_name="PortfolioTaxLotWindow",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=CLIENT_SENSITIVE,
        retention_requirement=RETAIN_FOR_CLIENT_RECORD,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
        pii_fields=("portfolio_id", "tax_lot_id"),
    ),
    SourceDataSecurityProfile(
        product_name="MarketDataCoverageWindow",
        tenant_required=True,
        entitlement_required=True,
        access_classification=SYSTEM_ACCESS,
        sensitivity_classification=REFERENCE_INTERNAL,
        retention_requirement=RETAIN_FOR_SOURCE_AUDIT,
        audit_requirement=AUDIT_SYSTEM_ACCESS,
    ),
)


def get_source_data_security_profile(product_name: str) -> SourceDataSecurityProfile:
    requested = _normalize_required_text(product_name, "product_name")
    for profile in SOURCE_DATA_SECURITY_PROFILES:
        if profile.product_name.upper() == requested:
            return profile
    raise KeyError(f"Unknown source-data security profile: {product_name}")


def source_data_security_openapi_extra(product_name: str) -> dict[str, dict[str, object]]:
    profile = get_source_data_security_profile(product_name)
    return {
        "x-lotus-source-data-security": {
            "product_name": profile.product_name,
            "tenant_required": profile.tenant_required,
            "entitlement_required": profile.entitlement_required,
            "access_classification": profile.access_classification,
            "sensitivity_classification": profile.sensitivity_classification,
            "retention_requirement": profile.retention_requirement,
            "audit_requirement": profile.audit_requirement,
            "required_capability": required_source_data_capability(profile.product_name),
            "pii_fields": list(profile.pii_fields),
            "operator_only": profile.operator_only,
        }
    }


def required_source_data_capability(product_name: str) -> str:
    get_source_data_security_profile(product_name)
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", product_name).lower()
    return f"source_data.{normalized}.read"


def source_data_capability_rules() -> dict[str, str]:
    rules: dict[str, str] = {}
    for product in SOURCE_DATA_PRODUCT_CATALOG:
        capability = required_source_data_capability(product.product_name)
        for route in product.current_routes:
            for method in SOURCE_DATA_READ_METHODS:
                rules[f"{method} {route}"] = capability
    return rules


def validate_source_data_security_profiles(
    profiles: tuple[SourceDataSecurityProfile, ...] = SOURCE_DATA_SECURITY_PROFILES,
) -> None:
    _validate_source_data_security_profiles(profiles, catalog=SOURCE_DATA_PRODUCT_CATALOG)


def validate_dpm_planned_source_data_security_profiles(
    profiles: tuple[SourceDataSecurityProfile, ...] = DPM_PLANNED_SOURCE_DATA_SECURITY_PROFILES,
) -> None:
    _validate_source_data_security_profiles(
        profiles,
        catalog=DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG,
    )


def _validate_source_data_security_profiles(
    profiles: tuple[SourceDataSecurityProfile, ...],
    *,
    catalog: tuple[SourceDataProductDefinition, ...],
) -> None:
    catalog_products = {product.product_name.upper(): product for product in catalog}
    catalog_product_names = {
        product_name: product.product_name for product_name, product in catalog_products.items()
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
        catalog_product = catalog_products.get(product_name)
        if profile.operator_only and profile.access_classification != OPERATOR_ACCESS:
            raise ValueError(f"{profile.product_name} operator_only requires operator access")
        if profile.operator_only:
            if catalog_product and catalog_product.route_family != CONTROL_PLANE_AND_POLICY:
                raise ValueError(
                    f"{profile.product_name} operator_only requires control-plane route family"
                )
        if profile.audit_requirement == AUDIT_OPERATOR_ACCESS and not profile.operator_only:
            raise ValueError(f"{profile.product_name} operator audit requires operator_only")
        expected_audit_requirement = ACCESS_CLASSIFICATION_AUDIT_REQUIREMENT[
            profile.access_classification
        ]
        if profile.audit_requirement != expected_audit_requirement:
            raise ValueError(
                f"{profile.product_name} audit_requirement {profile.audit_requirement} "
                f"is not valid for access_classification {profile.access_classification}"
            )
        expected_retention_requirement = SENSITIVITY_RETENTION_REQUIREMENT[
            profile.sensitivity_classification
        ]
        if profile.retention_requirement != expected_retention_requirement:
            raise ValueError(
                f"{profile.product_name} retention_requirement "
                f"{profile.retention_requirement} is not valid for sensitivity_classification "
                f"{profile.sensitivity_classification}"
            )
        if catalog_product:
            allowed_route_families = ACCESS_CLASSIFICATION_ROUTE_FAMILIES[
                profile.access_classification
            ]
            if catalog_product.route_family not in allowed_route_families:
                raise ValueError(
                    f"{profile.product_name} access_classification "
                    f"{profile.access_classification} is not valid for route family "
                    f"{catalog_product.route_family}"
                )
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
