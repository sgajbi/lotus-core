import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ClientTaxRuleSetRequest,
)
from src.services.query_service.app.services.client_tax_rule_set import (
    build_client_tax_rule_set_response,
    resolve_client_tax_rule_set_response,
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
    assert response.source_batch_fingerprint is None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("client_tax_rule_set:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "client_tax_rule_sets,portfolio_mandate_bindings",
        "contract_version": "rfc_042_client_tax_rule_set_v1",
    }


def test_resolve_client_tax_rule_set_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self, **kwargs: object
            ) -> SimpleNamespace:
                calls.append(("binding", kwargs))
                return _binding()

            async def list_client_tax_rule_sets(self, **kwargs: object) -> list[SimpleNamespace]:
                calls.append(("rules", kwargs))
                return [_tax_rule_row()]

        response = await resolve_client_tax_rule_set_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is not None
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert calls == [
        (
            "binding",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
            },
        ),
        (
            "rules",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_rules": False,
            },
        ),
    ]


def test_resolve_client_tax_rule_set_response_skips_rows_without_binding() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(self, **_: object) -> None:
                calls.append("binding")
                return None

            async def list_client_tax_rule_sets(self, **_: object) -> list[object]:
                calls.append("rules")
                raise AssertionError("Unexpected tax-rule read without mandate binding")

        response = await resolve_client_tax_rule_set_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["binding"]


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
