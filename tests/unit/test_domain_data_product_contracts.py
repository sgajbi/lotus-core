from __future__ import annotations

import json

import pytest
from portfolio_common.source_data_products import (
    ANALYTICS_INPUT,
    CONTROL_PLANE_AND_POLICY,
    DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG,
    OPERATIONAL_READ,
    QUERY_CONTROL_PLANE_SERVICE,
    QUERY_SERVICE,
    SNAPSHOT_AND_SIMULATION,
    SOURCE_DATA_PRODUCT_CATALOG,
)
from portfolio_common.source_data_security import (
    DPM_PLANNED_SOURCE_DATA_SECURITY_PROFILES,
    get_source_data_security_profile,
)

from scripts.validate_domain_data_product_contracts import (
    LOCAL_DECLARATION_DIR,
    platform_validation_dependencies_available,
    validate_repo_native_contracts,
)

DECLARATION_PATH = LOCAL_DECLARATION_DIR / "lotus-core-products.v1.json"


def _load_declaration() -> dict:
    return json.loads(DECLARATION_PATH.read_text(encoding="utf-8"))


def test_repo_native_domain_data_product_validation_passes_when_platform_is_available() -> None:
    if not platform_validation_dependencies_available():
        pytest.skip("lotus-platform validation dependencies are not available in this environment")

    assert validate_repo_native_contracts() == []


def test_repo_native_domain_data_product_directory_contains_core_declaration() -> None:
    declaration_names = {path.name for path in LOCAL_DECLARATION_DIR.glob("*.json")}

    assert declaration_names == {"lotus-core-products.v1.json"}


def test_core_domain_product_declaration_aligns_to_live_source_data_catalog() -> None:
    declaration = _load_declaration()
    declared_by_name = {product["product_name"]: product for product in declaration["products"]}
    active_declared_by_name = {
        product_name: product
        for product_name, product in declared_by_name.items()
        if product["lifecycle_status"] == "active"
    }
    family_map = {
        OPERATIONAL_READ: "operational_source_data",
        SNAPSHOT_AND_SIMULATION: "simulation_and_projected_state",
        ANALYTICS_INPUT: "analytics_input",
        CONTROL_PLANE_AND_POLICY: "supportability_and_control_plane",
    }

    assert declaration["producer_repository"] == "lotus-core"
    assert declaration["authoritative_domain"] == "portfolio_state"
    assert set(active_declared_by_name) == {
        product.product_name for product in SOURCE_DATA_PRODUCT_CATALOG
    }

    for source_product in SOURCE_DATA_PRODUCT_CATALOG:
        declared = active_declared_by_name[source_product.product_name]
        profile = get_source_data_security_profile(source_product.product_name)

        assert declared["product_version"] == source_product.product_version
        assert declared["owner_repository"] == source_product.owner
        expected_family = (
            "dpm_source_data"
            if source_product.product_name
            in {
                "DpmModelPortfolioTarget",
                "DiscretionaryMandateBinding",
                "InstrumentEligibilityProfile",
                "PortfolioTaxLotWindow",
                "TransactionCostCurve",
                "MarketDataCoverageWindow",
                "DpmSourceReadiness",
                "PortfolioManagerBookMembership",
                "CioModelChangeAffectedCohort",
                "ClientRestrictionProfile",
                "SustainabilityPreferenceProfile",
            }
            else family_map[source_product.route_family]
        )
        assert declared["product_family"] == expected_family
        assert declared["approved_consumers"] == list(source_product.consumers)
        assert declared["required_trust_metadata"] == list(source_product.required_metadata_fields)
        assert declared["serving_plane"] == source_product.serving_plane
        assert declared["current_routes"] == list(source_product.current_routes)
        assert declared["security_profile_ref"] == (
            f"{profile.access_classification}:{profile.sensitivity_classification}:"
            f"{profile.retention_requirement}:{profile.audit_requirement}"
        )


def test_core_domain_product_declaration_aligns_to_planned_dpm_source_products() -> None:
    declaration = _load_declaration()
    proposed_declared_by_name = {
        product["product_name"]: product
        for product in declaration["products"]
        if product["lifecycle_status"] == "proposed"
    }
    profiles = {
        profile.product_name: profile for profile in DPM_PLANNED_SOURCE_DATA_SECURITY_PROFILES
    }

    assert set(proposed_declared_by_name) == {
        product.product_name for product in DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG
    }

    for source_product in DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG:
        declared = proposed_declared_by_name[source_product.product_name]
        profile = profiles[source_product.product_name]

        assert declared["product_version"] == source_product.product_version
        assert declared["owner_repository"] == source_product.owner
        assert declared["product_family"] == "dpm_source_data"
        assert declared["approved_consumers"] == list(source_product.consumers)
        assert declared["required_trust_metadata"] == list(source_product.required_metadata_fields)
        assert declared["serving_plane"] == source_product.serving_plane
        assert declared["current_routes"] == list(source_product.current_routes)
        assert declared["security_profile_ref"] == (
            f"{profile.access_classification}:{profile.sensitivity_classification}:"
            f"{profile.retention_requirement}:{profile.audit_requirement}"
        )


def test_core_declaration_preserves_high_value_mesh_products_and_trust_posture() -> None:
    products = {product["product_name"]: product for product in _load_declaration()["products"]}

    assert products["PortfolioStateSnapshot"]["identifier_refs"] == [
        "portfolio_id",
        "snapshot_id",
        "tenant_id",
    ]
    assert products["PortfolioStateSnapshot"]["temporal_semantics_ref"] == "as_of_date"
    assert products["HoldingsAsOf"]["serving_plane"] == QUERY_SERVICE
    assert products["TransactionLedgerWindow"]["serving_plane"] == QUERY_SERVICE
    assert products["PortfolioCashflowProjection"]["serving_plane"] == QUERY_SERVICE
    assert products["PortfolioLiquidityLadder"]["serving_plane"] == QUERY_SERVICE
    assert products["MarketDataWindow"]["temporal_semantics_ref"] == "valuation_date"
    assert products["RiskFreeSeriesWindow"]["request_scope"]["scope_level"] == "global"
    assert products["PortfolioTimeseriesInput"]["serving_plane"] == QUERY_CONTROL_PLANE_SERVICE
    assert products["PositionTimeseriesInput"]["serving_plane"] == QUERY_CONTROL_PLANE_SERVICE

    for evidence_product in (
        "ReconciliationEvidenceBundle",
        "DataQualityCoverageReport",
        "IngestionEvidenceBundle",
    ):
        assert (
            products[evidence_product]["lineage_policy"]["evidence_access_class_ref"]
            == "operator_only"
        )
        assert products[evidence_product]["lineage_policy"]["evidence_bundle_required"] is True


def test_core_declaration_readme_documents_local_validation_path() -> None:
    readme = (LOCAL_DECLARATION_DIR / "README.md").read_text(encoding="utf-8")

    assert "python scripts/validate_domain_data_product_contracts.py" in readme
    assert "make domain-product-validate" in readme
    assert "source_data_products.py" in readme
