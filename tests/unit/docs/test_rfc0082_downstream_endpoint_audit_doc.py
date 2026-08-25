from pathlib import Path

from portfolio_common.source_data_products import (
    QUERY_CONTROL_PLANE_SERVICE,
    SOURCE_DATA_PRODUCT_CATALOG,
)

AUDIT_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "architecture"
    / "RFC-0082-downstream-endpoint-consumer-and-test-coverage-audit.md"
)


def test_downstream_endpoint_audit_covers_query_control_plane_catalog():
    audit_text = AUDIT_DOC.read_text(encoding="utf-8")

    for product in SOURCE_DATA_PRODUCT_CATALOG:
        if product.serving_plane != QUERY_CONTROL_PLANE_SERVICE:
            continue

        assert product.product_name in audit_text
        for route in product.current_routes:
            assert route in audit_text
        for consumer in product.consumers:
            assert consumer in audit_text


def test_downstream_endpoint_audit_records_validation_posture():
    audit_text = AUDIT_DOC.read_text(encoding="utf-8")

    required_evidence = {
        "Swagger Documentation Assessment",
        "Test Pyramid Assessment",
        "python scripts\\openapi_quality_gate.py",
        "python scripts\\source_data_product_contract_guard.py",
        "python scripts\\analytics_input_consumer_contract_guard.py",
        "PB_SG_GLOBAL_BAL_001",
        "live end-to-end",
        "RFC-0083-platform-e2e-runtime-validation-evidence.md",
    }

    missing_evidence = sorted(
        evidence for evidence in required_evidence if evidence not in audit_text
    )

    assert missing_evidence == []


def test_downstream_endpoint_audit_pins_gateway_consumer_rows_to_catalog() -> None:
    audit_text = AUDIT_DOC.read_text(encoding="utf-8")
    gateway_products = {
        "PortfolioAnalyticsReference",
        "BenchmarkAssignment",
        "BenchmarkDefinition",
        "ExternalOrderExecutionAcknowledgement",
    }

    rows = {
        product: next(row for row in audit_text.splitlines() if row.startswith(f"| `{product}` |"))
        for product in gateway_products
    }

    for product in SOURCE_DATA_PRODUCT_CATALOG:
        if product.product_name not in gateway_products:
            continue
        intended_consumers_cell = rows[product.product_name].split("|")[3]
        assert "lotus-gateway" in intended_consumers_cell


def test_downstream_endpoint_audit_preserves_performance_output_boundary():
    audit_text = AUDIT_DOC.read_text(encoding="utf-8").lower()

    required_boundary_lines = {
        "performance snapshot",
        "portfolio return",
        "benchmark return",
        "excess return",
        "lotus-performance",
    }

    missing_lines = sorted(line for line in required_boundary_lines if line not in audit_text)

    assert missing_lines == []
