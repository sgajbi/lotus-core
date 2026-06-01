from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ClientTaxRuleSetRequest,
)
from src.services.query_service.app.services.client_tax_rule_set import (
    build_client_tax_rule_set_response,
)


def _binding(as_of_date: date = date(2026, 5, 3)) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        effective_from=as_of_date,
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _tax_rule_row() -> SimpleNamespace:
    return SimpleNamespace(
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


def _request() -> ClientTaxRuleSetRequest:
    return ClientTaxRuleSetRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


def test_build_client_tax_rule_set_response_marks_ready() -> None:
    response = build_client_tax_rule_set_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[_tax_rule_row()],
    )

    assert response.product_name == "ClientTaxRuleSet"
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "CLIENT_TAX_RULE_SET_READY"
    assert response.supportability.rule_count == 1
    assert response.supportability.missing_data_families == []
    assert response.rules[0].rule_code == "US_DIVIDEND_WITHHOLDING"
    assert response.rules[0].rate == Decimal("0.1500000000")
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("client_tax_rule_set:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "client_tax_rule_sets,portfolio_mandate_bindings",
        "contract_version": "rfc_042_client_tax_rule_set_v1",
    }


def test_build_client_tax_rule_set_response_marks_empty_missing() -> None:
    response = build_client_tax_rule_set_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[],
    )

    assert response.rules == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_TAX_RULE_SET_EMPTY"
    assert response.supportability.rule_count == 0
    assert response.supportability.missing_data_families == ["client_tax_rule_set"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)
