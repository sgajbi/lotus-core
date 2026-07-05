from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.services.ingestion_service.app.application.reference_data_ingestion_registry import (
    REFERENCE_DATA_INGESTION_REGISTRY,
)

EXPECTED_COMMANDS = {
    "benchmark_assignment": (
        "/ingest/benchmark-assignments",
        "benchmark_assignment",
        "benchmark_assignments",
        "upsert_portfolio_benchmark_assignments",
    ),
    "model_portfolio": (
        "/ingest/model-portfolios",
        "model_portfolio",
        "model_portfolios",
        "upsert_model_portfolio_definitions",
    ),
    "model_portfolio_target": (
        "/ingest/model-portfolio-targets",
        "model_portfolio_target",
        "model_portfolio_targets",
        "upsert_model_portfolio_targets",
    ),
    "instrument_eligibility_profile": (
        "/ingest/instrument-eligibility",
        "instrument_eligibility_profile",
        "eligibility_profiles",
        "upsert_instrument_eligibility_profiles",
    ),
    "mandate_binding": (
        "/ingest/mandate-bindings",
        "mandate_binding",
        "mandate_bindings",
        "upsert_discretionary_mandate_bindings",
    ),
    "client_restriction_profile": (
        "/ingest/client-restriction-profiles",
        "client_restriction_profile",
        "restriction_profiles",
        "upsert_client_restriction_profiles",
    ),
    "sustainability_preference_profile": (
        "/ingest/sustainability-preferences",
        "sustainability_preference_profile",
        "sustainability_preferences",
        "upsert_sustainability_preference_profiles",
    ),
    "client_tax_profile": (
        "/ingest/client-tax-profiles",
        "client_tax_profile",
        "tax_profiles",
        "upsert_client_tax_profiles",
    ),
    "client_tax_rule_set": (
        "/ingest/client-tax-rule-sets",
        "client_tax_rule_set",
        "tax_rule_sets",
        "upsert_client_tax_rule_sets",
    ),
    "client_income_needs_schedule": (
        "/ingest/client-income-needs-schedules",
        "client_income_needs_schedule",
        "income_needs_schedules",
        "upsert_client_income_needs_schedules",
    ),
    "liquidity_reserve_requirement": (
        "/ingest/liquidity-reserve-requirements",
        "liquidity_reserve_requirement",
        "liquidity_reserve_requirements",
        "upsert_liquidity_reserve_requirements",
    ),
    "planned_withdrawal_schedule": (
        "/ingest/planned-withdrawal-schedules",
        "planned_withdrawal_schedule",
        "planned_withdrawal_schedules",
        "upsert_planned_withdrawal_schedules",
    ),
    "benchmark_definition": (
        "/ingest/benchmark-definitions",
        "benchmark_definition",
        "benchmark_definitions",
        "upsert_benchmark_definitions",
    ),
    "benchmark_composition": (
        "/ingest/benchmark-compositions",
        "benchmark_composition",
        "benchmark_compositions",
        "upsert_benchmark_compositions",
    ),
    "index_definition": (
        "/ingest/indices",
        "index_definition",
        "indices",
        "upsert_indices",
    ),
    "index_price_series": (
        "/ingest/index-price-series",
        "index_price_series",
        "index_price_series",
        "upsert_index_price_series",
    ),
    "index_return_series": (
        "/ingest/index-return-series",
        "index_return_series",
        "index_return_series",
        "upsert_index_return_series",
    ),
    "benchmark_return_series": (
        "/ingest/benchmark-return-series",
        "benchmark_return_series",
        "benchmark_return_series",
        "upsert_benchmark_return_series",
    ),
    "risk_free_series": (
        "/ingest/risk-free-series",
        "risk_free_series",
        "risk_free_series",
        "upsert_risk_free_series",
    ),
    "classification_taxonomy": (
        "/ingest/reference/classification-taxonomy",
        "classification_taxonomy",
        "classification_taxonomy",
        "upsert_classification_taxonomy",
    ),
    "cash_account_master": (
        "/ingest/reference/cash-accounts",
        "cash_account_master",
        "cash_accounts",
        "upsert_cash_account_masters",
    ),
    "instrument_lookthrough_component": (
        "/ingest/reference/instrument-lookthrough-components",
        "instrument_lookthrough_component",
        "lookthrough_components",
        "upsert_instrument_lookthrough_components",
    ),
}


class _FakeRecord:
    def __init__(self, record_id: str) -> None:
        self.record_id = record_id
        self.dump_kwargs: list[dict[str, Any]] = []

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        self.dump_kwargs.append(kwargs)
        return {"record_id": self.record_id}


class _FakePayload:
    def __init__(self, records_attribute: str, records: list[_FakeRecord]) -> None:
        self.payload_dump_kwargs: list[dict[str, Any]] = []
        setattr(self, records_attribute, records)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        self.payload_dump_kwargs.append(kwargs)
        return {"payload": "json"}


class _CapturingReferenceDataService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []

    def __getattr__(self, method_name: str) -> Any:
        if not method_name.startswith("upsert_"):
            raise AttributeError(method_name)

        async def _persist(records: list[dict[str, Any]]) -> None:
            self.calls.append((method_name, records))

        return _persist


def test_reference_data_registry_pins_all_family_mappings_without_fastapi() -> None:
    commands = {
        command.command_key: (
            command.endpoint,
            command.entity_type,
            command.records_attribute,
            command.persist_method_name,
        )
        for command in REFERENCE_DATA_INGESTION_REGISTRY.all_commands()
    }

    assert commands == EXPECTED_COMMANDS


@pytest.mark.asyncio
async def test_reference_data_command_dispatches_to_service_with_preserved_record_dump() -> None:
    command = REFERENCE_DATA_INGESTION_REGISTRY.require("cash_account_master")
    records = [_FakeRecord("CASH_1"), _FakeRecord("CASH_2")]
    payload = _FakePayload("cash_accounts", records)
    service = _CapturingReferenceDataService()

    assert command.accepted_count(payload) == 2
    assert command.request_payload(payload) == {"payload": "json"}
    await command.persist(service, payload)

    assert payload.payload_dump_kwargs == [{"mode": "json"}]
    assert records[0].dump_kwargs == [{}]
    assert records[1].dump_kwargs == [{}]
    assert service.calls == [
        (
            "upsert_cash_account_masters",
            [{"record_id": "CASH_1"}, {"record_id": "CASH_2"}],
        )
    ]


def test_reference_data_registry_rejects_unknown_command_key() -> None:
    with pytest.raises(KeyError, match="Unknown reference-data ingestion command"):
        REFERENCE_DATA_INGESTION_REGISTRY.require("unknown_reference_family")


def test_reference_data_router_does_not_encode_persistence_mapping() -> None:
    router_source = Path("src/services/ingestion_service/app/routers/reference_data.py").read_text(
        encoding="utf-8"
    )

    assert "persist_fn" not in router_source
    assert "lambda: reference_data_service" not in router_source
    assert "upsert_" not in router_source
