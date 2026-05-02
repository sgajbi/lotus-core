from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT / "docs" / "standards" / "rfc-087-dpm-source-product-spec.v1.json"
RFC_PATH = (
    ROOT
    / "docs"
    / "RFCs"
    / "RFC 087 - DPM Source Data Products for lotus-manage Stateful Execution.md"
)

EXPECTED_PRODUCTS = {
    "DpmModelPortfolioTarget": "Slice 4",
    "DiscretionaryMandateBinding": "Slice 5",
    "InstrumentEligibilityProfile": "Slice 6",
    "PortfolioTaxLotWindow": "Slice 7",
    "MarketDataCoverageWindow": "Slice 8",
}


def _load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_rfc087_dpm_source_product_spec_is_complete_and_slice_aligned() -> None:
    spec = _load_spec()
    products = {product["product_name"]: product for product in spec["products"]}

    assert spec["contract_id"] == "lotus-core-rfc-087-dpm-source-product-spec"
    assert spec["governed_by_rfc"] == "RFC-087"
    assert products.keys() == EXPECTED_PRODUCTS.keys()

    for product_name, implementation_slice in EXPECTED_PRODUCTS.items():
        product = products[product_name]
        assert product["product_version"] == "v1"
        assert product["product_family"] == "dpm_source_data"
        assert product["implementation_slice"] == implementation_slice
        assert product["proposed_route"]["method"] == "POST"
        assert product["proposed_route"]["path"].startswith("/integration/")
        assert product["required_ingestion"]
        assert len(product["minimum_response_families"]) >= 5


def test_rfc087_dpm_source_product_spec_blocks_monolithic_context_route() -> None:
    spec = _load_spec()
    all_routes = {product["proposed_route"]["path"] for product in spec["products"]}

    assert spec["architecture_decisions"]["monolithic_execution_context_route_allowed"] is False
    assert not any("dpm-execution-context" in route for route in all_routes)
    assert not any("execution-context" in route for route in all_routes)


def test_rfc087_dpm_source_product_spec_keeps_certification_controls_mandatory() -> None:
    spec = _load_spec()
    certification = spec["certification_requirements"]

    assert certification == {
        "api_certification_required": True,
        "openapi_quality_required": True,
        "source_data_product_contract_guard_required": True,
        "domain_product_validation_required": True,
        "trust_telemetry_required": True,
        "mesh_certification_required": True,
        "live_canonical_evidence_required": True,
        "duplicate_endpoint_review_required": True,
    }


def test_rfc087_dpm_source_product_spec_matches_rfc_product_names() -> None:
    rfc = RFC_PATH.read_text(encoding="utf-8")
    spec = _load_spec()

    assert str(SPEC_PATH.relative_to(ROOT)).replace("\\", "/") in rfc
    for product in spec["products"]:
        assert f"`{product['product_name']}:v1`" in rfc
